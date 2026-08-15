from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, Awaitable, Callable
from time import monotonic
from typing import Any

from echoscene_core.environment import apply_environment
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    ModelSettings,
    RoomInputOptions,
    cli,
    llm,
)
from livekit.agents.metrics import EOUMetrics

from .controller import (
    CoachingActionKind,
    TrainingController,
    TrainingState,
)
from .prompts.voice_coach_v1 import (
    PROMPT_VERSION,
    build_turn_feedback_instruction,
    build_voice_coach_instructions,
)
from .provider_config import provider_config
from .voice_events import (
    AgentStateVoiceEvent,
    ExerciseCompletedVoiceEvent,
    InterruptionVoiceEvent,
    SessionRecordVoiceEvent,
    TrainingActionVoiceEvent,
    TranscriptVoiceEvent,
    VoiceEndpointingEvent,
    VoiceEvent,
    VoiceLatencyEvent,
    VoiceRecordTurn,
)

server = AgentServer()


def parse_job_metadata(raw_metadata: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_metadata or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_voice_opening(metadata: dict[str, Any]) -> str:
    task = metadata.get("task") if isinstance(metadata.get("task"), dict) else {}
    prompt = str(
        task.get("prompt") or "Explain the main idea from the video in your own words."
    ).strip()
    guidance_language = str(metadata.get("guidanceLanguage") or "zh-Hans")
    if guidance_language.lower().startswith("zh"):
        return f"现在开始练习。请用英语回答：{prompt}"
    return f"Let's begin. {prompt}"


def assistant_transcript_text(item: Any) -> str | None:
    if not isinstance(item, llm.ChatMessage) or item.role != "assistant":
        return None
    text = (item.text_content or "").strip()
    return text or None


def parse_voice_control(payload: bytes) -> str | None:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict) or decoded.get("schemaVersion") != "1.0":
        return None
    control_type = decoded.get("type")
    return control_type if control_type in {"retry-response", "commit-turn"} else None


class EchoSceneCoach(Agent):
    def __init__(self, metadata: dict[str, Any]) -> None:
        super().__init__(instructions=build_voice_coach_instructions(metadata))
        self.controller = TrainingController()
        self.last_learner_transcript = ""
        task = metadata.get("task") if isinstance(metadata.get("task"), dict) else {}
        self.coaching_focus = str(
            task.get("coachingFocus") or "State the central idea clearly and use one example."
        )
        self.pending_action: CoachingActionKind | None = None
        self.assessment_started_at: float | None = None
        self.first_feedback_token_at: float | None = None
        self.learner_turn_count = 0
        self.session_record: list[VoiceRecordTurn] = []
        self._event_publisher: Callable[[VoiceEvent], Awaitable[None]] | None = None
        self._event_queue: asyncio.Queue[VoiceEvent] | None = None
        self._event_worker: asyncio.Task[None] | None = None

    def set_event_publisher(self, publisher: Callable[[VoiceEvent], Awaitable[None]]) -> None:
        self._event_publisher = publisher

    def publish_event_without_blocking_audio(self, event: VoiceEvent) -> None:
        """Serialize UI events off the LLM-to-TTS critical path."""
        if self._event_publisher is None:
            return
        if self._event_queue is None:
            self._event_queue = asyncio.Queue()
        self._event_queue.put_nowait(event)
        if self._event_worker is None or self._event_worker.done():
            self._event_worker = asyncio.create_task(self._drain_event_queue())

    async def _drain_event_queue(self) -> None:
        if self._event_queue is None or self._event_publisher is None:
            return
        try:
            while not self._event_queue.empty():
                event = await self._event_queue.get()
                try:
                    await self._event_publisher(event)
                except Exception:
                    # A caption/metric delivery failure must never interrupt synthesized audio.
                    pass
                finally:
                    self._event_queue.task_done()
        finally:
            self._event_worker = None

    async def drain_event_publications(self) -> None:
        if self._event_queue is not None:
            await self._event_queue.join()

    async def on_enter(self) -> None:
        self.controller.transition(TrainingState.PREPARING, "room context received")
        self.controller.transition(TrainingState.BRIEFING, "grounded task available")
        self.controller.transition(TrainingState.PROMPTING, "coach introduces task")
        self.controller.transition(TrainingState.LISTENING, "learner turn opened")

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        _ = turn_ctx
        if self.controller.state is not TrainingState.LISTENING:
            return
        self.last_learner_transcript = new_message.text_content or ""
        self.learner_turn_count += 1
        if self.last_learner_transcript.strip():
            self.session_record.append(
                VoiceRecordTurn(
                    role="learner",
                    text=self.last_learner_transcript.strip(),
                    turn_count=self.learner_turn_count,
                )
            )
        self.controller.transition(TrainingState.ASSESSING, "learner turn completed")
        self.assessment_started_at = monotonic()
        self.first_feedback_token_at = None

    def llm_node(self, chat_ctx, tools, model_settings):
        if self.controller.state in {TrainingState.COMPLETED, TrainingState.ERROR}:
            return None
        if self.controller.state is not TrainingState.ASSESSING:
            return Agent.default.llm_node(self, chat_ctx, tools, model_settings)
        action = self.controller.next_coaching_action(self.last_learner_transcript)
        self.controller.apply_coaching_action(
            action,
            "deterministic bounded move selected before feedback generation",
        )
        self.pending_action = action
        feedback_ctx = chat_ctx.copy(exclude_function_call=True, tools=[])
        feedback_ctx.add_message(
            role="system",
            content=build_turn_feedback_instruction(
                action.value,
                self.last_learner_transcript,
                self.coaching_focus,
            ),
        )
        if self._event_publisher is not None:
            self.publish_event_without_blocking_audio(
                TrainingActionVoiceEvent(
                    action=action,
                    training_state=self.controller.state,
                    turn_count=self.learner_turn_count,
                )
            )
        return Agent.default.llm_node(
            self,
            feedback_ctx,
            [],
            ModelSettings(tool_choice="none"),
        )

    async def transcription_node(self, text: AsyncIterable, model_settings: ModelSettings):
        response_parts: list[str] = []
        last_interim_length = 0
        async for delta in Agent.default.transcription_node(self, text, model_settings):
            part = str(delta)
            if part:
                response_parts.append(part)
                if self.first_feedback_token_at is None:
                    self.first_feedback_token_at = monotonic()
                    if self._event_publisher is not None and self.assessment_started_at is not None:
                        self.publish_event_without_blocking_audio(
                            VoiceLatencyEvent(
                                phase="feedback-first-token",
                                duration_ms=round(
                                    (self.first_feedback_token_at - self.assessment_started_at)
                                    * 1000
                                ),
                            )
                        )
                interim = "".join(response_parts).strip()
                should_publish_interim = len(
                    interim
                ) - last_interim_length >= 12 or interim.endswith((".", "?", "!", "。", "？", "！"))
                if interim and should_publish_interim and self._event_publisher is not None:
                    self.publish_event_without_blocking_audio(
                        TranscriptVoiceEvent(
                            role="coach",
                            text=interim,
                            is_final=False,
                        )
                    )
                    last_interim_length = len(interim)
            yield delta
        response = "".join(response_parts).strip()
        exercise_completed = self.pending_action is CoachingActionKind.COMPLETE
        if response and self._event_publisher is not None:
            self.session_record.append(
                VoiceRecordTurn(
                    role="coach",
                    text=response,
                    turn_count=self.learner_turn_count,
                )
            )
            self.publish_event_without_blocking_audio(
                TranscriptVoiceEvent(role="coach", text=response, is_final=True)
            )
            if self.assessment_started_at is not None:
                self.publish_event_without_blocking_audio(
                    VoiceLatencyEvent(
                        phase="feedback-complete",
                        duration_ms=round((monotonic() - self.assessment_started_at) * 1000),
                    )
                )
            self.publish_event_without_blocking_audio(
                SessionRecordVoiceEvent(entries=self.session_record.copy())
            )
            if exercise_completed:
                self.publish_event_without_blocking_audio(
                    ExerciseCompletedVoiceEvent(
                        turn_count=self.learner_turn_count,
                        max_turns=4,
                    )
                )
        if response:
            self.pending_action = None


async def publish_voice_event(ctx: JobContext, event: VoiceEvent) -> None:
    reliable = not (isinstance(event, TranscriptVoiceEvent) and not event.is_final)
    await ctx.room.local_participant.publish_data(
        event.wire_json(),
        reliable=reliable,
        topic="echoscene.voice.v1",
    )


def register_voice_observers(session: AgentSession, ctx: JobContext, coach: EchoSceneCoach) -> None:
    coach.set_event_publisher(lambda event: publish_voice_event(ctx, event))

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        if not event.transcript.strip():
            return
        asyncio.create_task(
            publish_voice_event(
                ctx,
                TranscriptVoiceEvent(
                    role="learner",
                    text=event.transcript.strip(),
                    is_final=event.is_final,
                    language=str(event.language) if event.language else None,
                ),
            )
        )

    @session.on("conversation_item_added")
    def on_conversation_item_added(event) -> None:
        text = assistant_transcript_text(event.item)
        if text is None:
            return
        asyncio.create_task(
            publish_voice_event(
                ctx,
                TranscriptVoiceEvent(role="coach", text=text, is_final=True),
            )
        )

    @session.on("agent_state_changed")
    def on_agent_state_changed(event) -> None:
        asyncio.create_task(
            publish_voice_event(
                ctx,
                AgentStateVoiceEvent(
                    agent_state=event.new_state,
                    training_state=coach.controller.state,
                ),
            )
        )

    @session.on("metrics_collected")
    def on_metrics_collected(event) -> None:
        if not isinstance(event.metrics, EOUMetrics):
            return
        asyncio.create_task(
            publish_voice_event(
                ctx,
                VoiceEndpointingEvent(
                    end_of_utterance_delay_ms=round(event.metrics.end_of_utterance_delay * 1000),
                    transcription_delay_ms=round(event.metrics.transcription_delay * 1000),
                ),
            )
        )

    @session.on("error")
    def on_error(event) -> None:
        # A provider failure during assessment is recoverable via the existing retry-response
        # control. Keep the finalized transcript and ASSESSING state intact.
        if coach.pending_action is not None:
            error_state = TrainingState.ASSESSING
        elif coach.controller.state not in {TrainingState.COMPLETED, TrainingState.ERROR}:
            try:
                coach.controller.transition(
                    TrainingState.ERROR,
                    f"voice provider error: {type(event.error).__name__}",
                )
            except ValueError:
                pass
            error_state = TrainingState.ERROR
        else:
            error_state = coach.controller.state
        asyncio.create_task(
            publish_voice_event(
                ctx,
                AgentStateVoiceEvent(
                    agent_state="idle",
                    training_state=error_state,
                ),
            )
        )

    @session.on("overlapping_speech")
    def on_overlapping_speech(event) -> None:
        if not event.is_interruption:
            return
        asyncio.create_task(
            publish_voice_event(
                ctx,
                InterruptionVoiceEvent(training_state=coach.controller.state),
            )
        )

    @ctx.room.on("data_received")
    def on_control_message(packet) -> None:
        if packet.topic != "echoscene.voice.control.v1":
            return
        control_type = parse_voice_control(packet.data)
        if control_type is None:
            return
        if control_type == "commit-turn":
            if coach.controller.state is TrainingState.LISTENING:
                session.commit_user_turn(
                    transcript_timeout=2.0,
                    stt_flush_duration=0.8,
                )
            return
        # Recovery is intentionally narrow: retry only the already-finalized learner turn and
        # preserve the deterministic controller state. The client never supplies replacement text.
        if coach.pending_action is None:
            return
        coach.assessment_started_at = monotonic()
        coach.first_feedback_token_at = None
        session.generate_reply(
            instructions=(
                build_turn_feedback_instruction(
                    coach.pending_action.value,
                    coach.last_learner_transcript,
                    coach.coaching_focus,
                )
            ),
            tool_choice="none",
            allow_interruptions=True,
        )


def describe_worker() -> dict[str, str | bool | None]:
    return {
        "stt": provider_config.stt,
        "stt_model": provider_config.stt_model,
        "llm": provider_config.llm,
        "llm_model": provider_config.llm_model,
        "tts": provider_config.tts,
        "tts_model": provider_config.tts_model,
        "tts_voice": provider_config.tts_voice,
        "prompt_version": PROMPT_VERSION,
        "demo_mode": provider_config.demo_mode,
    }


@server.rtc_session(agent_name="echoscene")
async def echoscene_session(ctx: JobContext) -> None:
    if provider_config.demo_mode:
        raise RuntimeError("EchoScene voice providers are still configured as mock")

    metadata = parse_job_metadata(ctx.job.metadata)
    coach = EchoSceneCoach(metadata)
    session = AgentSession(
        stt=provider_config.stt_model,
        llm=provider_config.llm_model,
        tts=provider_config.tts_model_string,
        turn_handling={
            "endpointing": {
                "mode": "dynamic",
                "min_delay": 0.45,
                "max_delay": 1.6,
                "alpha": 0.65,
            },
            "interruption": {
                "enabled": True,
                "mode": "adaptive",
                "min_duration": 0.8,
                "min_words": 2,
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.2,
                "backchannel_boundary": (1.25, 1.0),
            },
        },
    )
    register_voice_observers(session, ctx, coach)
    await session.start(
        room=ctx.room,
        agent=coach,
        record=False,
        room_input_options=RoomInputOptions(pre_connect_audio=False),
    )
    # The opening is deterministic and skips an unnecessary first LLM round-trip.
    # Publish the exact source text before TTS so the UI never needs to transcribe
    # synthesized coach audio back into a caption.
    opening = build_voice_opening(metadata)
    await publish_voice_event(
        ctx,
        TranscriptVoiceEvent(role="coach", text=opening, is_final=True),
    )
    session.say(opening, allow_interruptions=True, add_to_chat_ctx=False)


def run() -> None:
    # LiveKit's worker runner reads credentials directly from os.environ. EchoScene's
    # settings layer supports .env + .env.local merging, so bridge that resolved view
    # into the process before the SDK starts or creates job subprocesses.
    apply_environment()
    cli.run_app(server)


if __name__ == "__main__":
    run()
