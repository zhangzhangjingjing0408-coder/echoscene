import {
  voiceControlEventSchema,
  voiceRealtimeEventSchema,
  type VoiceTrainingAction
} from "@echoscene/contracts";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";

import { classifyMicrophoneError, VoiceSetupError } from "./voice-errors";

export type VoiceConnectionState =
  | "connecting"
  | "connected"
  | "agent-present"
  | "listening"
  | "thinking"
  | "response-error"
  | "speaking"
  | "completed"
  | "audio-blocked"
  | "agent-timeout"
  | "disconnected";

export type { VoiceTrainingAction };

export interface VoiceTranscriptEntry {
  id: string;
  role: "learner" | "coach";
  text: string;
  isFinal: boolean;
}

export type VoiceRoomEvent =
  | { type: "transcript"; entry: VoiceTranscriptEntry }
  | { type: "session-record"; entries: VoiceTranscriptEntry[] }
  | {
    type: "training-action";
    action: VoiceTrainingAction;
    trainingState: string;
    turnCount: number;
  }
  | { type: "interruption" }
  | { type: "exercise-completed"; turnCount: number; maxTurns: number }
  | { type: "endpointing"; endOfUtteranceDelayMs: number; transcriptionDelayMs: number }
  | { type: "latency"; phase: "feedback-first-token" | "feedback-complete"; durationMs: number };

export type DecodedVoiceEvent =
  | VoiceRoomEvent
  | { type: "agent-state"; state: VoiceConnectionState };

export function decodeVoiceEvent(payload: Uint8Array): DecodedVoiceEvent | null {
  let payloadJson: unknown;
  try {
    payloadJson = JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null;
  }
  const parsed = voiceRealtimeEventSchema.safeParse(payloadJson);
  if (!parsed.success) return null;
  const event = parsed.data;
  if (event.type === "agent-state") {
    const state = event.agentState === "idle" && event.trainingState === "assessing"
      ? "response-error"
      : event.agentState === "thinking"
      ? "thinking"
      : event.agentState === "speaking"
        ? "speaking"
        : event.agentState === "listening"
          ? "listening"
          : "agent-present";
    return { type: "agent-state", state };
  }
  if (event.type === "transcript") {
    return {
      type: "transcript",
      entry: {
        id: `${event.role}-${crypto.randomUUID()}`,
        role: event.role,
        text: event.text.trim(),
        isFinal: event.isFinal
      }
    };
  }
  if (event.type === "session-record") {
    return {
      type: "session-record",
      entries: event.entries.map((entry) => ({
        id: `${entry.role}-${entry.turnCount}`,
        role: entry.role,
        text: entry.text.trim(),
        isFinal: true
      }))
    };
  }
  if (event.type === "training-action") {
    return {
      type: "training-action",
      action: event.action,
      trainingState: event.trainingState,
      turnCount: event.turnCount
    };
  }
  if (event.type === "latency") {
    return { type: "latency", phase: event.phase, durationMs: event.durationMs };
  }
  if (event.type === "endpointing") {
    return {
      type: "endpointing",
      endOfUtteranceDelayMs: event.endOfUtteranceDelayMs,
      transcriptionDelayMs: event.transcriptionDelayMs
    };
  }
  if (event.type === "exercise-completed") {
    return {
      type: "exercise-completed",
      turnCount: event.turnCount,
      maxTurns: event.maxTurns
    };
  }
  return { type: "interruption" };
}

export class EchoSceneVoiceRoom {
  private readonly room = new Room({ adaptiveStream: true, dynacast: true });
  private attachedElements = new Set<HTMLMediaElement>();
  private agentTimer: number | undefined;
  private exerciseCompleted = false;

  constructor(
    private readonly onStateChange: (state: VoiceConnectionState) => void,
    private readonly onVoiceEvent: (event: VoiceRoomEvent) => void
  ) {
    this.room.on(RoomEvent.ParticipantConnected, () => {
      if (this.agentTimer !== undefined) window.clearTimeout(this.agentTimer);
      this.onStateChange(this.room.canPlaybackAudio ? "agent-present" : "audio-blocked");
    });
    this.room.on(RoomEvent.Disconnected, () => this.onStateChange("disconnected"));
    this.room.on(RoomEvent.TrackSubscribed, (track) => this.attachRemoteAudio(track));
    this.room.on(RoomEvent.TrackUnsubscribed, (track) => this.detachRemoteAudio(track));
    this.room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (!this.room.canPlaybackAudio) this.onStateChange("audio-blocked");
    });
    this.room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      if (topic !== "echoscene.voice.v1") return;
      this.handleData(payload);
    });
  }

  async connect(serverUrl: string, token: string): Promise<void> {
    this.exerciseCompleted = false;
    this.onStateChange("connecting");
    try {
      await this.room.connect(serverUrl, token);
    } catch (error) {
      throw new VoiceSetupError(
        "livekit_connection_failed",
        "The LiveKit room connection failed.",
        { cause: error }
      );
    }
    // This call remains inside the original click-driven async chain, so Chrome can
    // unlock remote audio before the Agent publishes its first track.
    await this.room.startAudio().catch(() => undefined);
    try {
      const publication = await this.room.localParticipant.setMicrophoneEnabled(true);
      if (!publication) {
        throw new VoiceSetupError(
          "microphone_unavailable",
          "Chrome did not create a microphone track."
        );
      }
    } catch (error) {
      await this.room.disconnect();
      if (error instanceof VoiceSetupError) throw error;
      throw new VoiceSetupError(
        classifyMicrophoneError(error),
        "The microphone could not be enabled.",
        { cause: error }
      );
    }
    if (!this.room.canPlaybackAudio) this.onStateChange("audio-blocked");
    else this.onStateChange(this.room.remoteParticipants.size ? "agent-present" : "connected");
    this.agentTimer = window.setTimeout(() => {
      if (this.room.remoteParticipants.size === 0) this.onStateChange("agent-timeout");
    }, 20_000);
  }

  async resumeAudio(): Promise<void> {
    await this.room.startAudio();
    this.onStateChange(this.room.remoteParticipants.size ? "agent-present" : "connected");
  }

  async requestCoachResponse(): Promise<void> {
    const event = voiceControlEventSchema.parse({
      schemaVersion: "1.0",
      type: "retry-response"
    });
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(JSON.stringify(event)),
      { reliable: true, topic: "echoscene.voice.control.v1" }
    );
  }

  async commitUserTurn(): Promise<void> {
    const event = voiceControlEventSchema.parse({
      schemaVersion: "1.0",
      type: "commit-turn"
    });
    await this.room.localParticipant.publishData(
      new TextEncoder().encode(JSON.stringify(event)),
      { reliable: true, topic: "echoscene.voice.control.v1" }
    );
  }

  async stopMicrophone(): Promise<void> {
    await this.room.localParticipant.setMicrophoneEnabled(false);
  }

  async disconnect(): Promise<void> {
    if (this.agentTimer !== undefined) window.clearTimeout(this.agentTimer);
    await this.room.localParticipant.setMicrophoneEnabled(false);
    await this.room.disconnect();
    this.attachedElements.forEach((element) => element.remove());
    this.attachedElements.clear();
  }

  private attachRemoteAudio(track: RemoteTrack): void {
    if (track.kind !== Track.Kind.Audio) return;
    const element = track.attach();
    element.dataset.echosceneAudio = "true";
    document.body.appendChild(element);
    void element.play().catch(() => this.onStateChange("audio-blocked"));
    this.attachedElements.add(element);
  }

  private detachRemoteAudio(track: RemoteTrack): void {
    track.detach().forEach((element) => {
      element.remove();
      this.attachedElements.delete(element);
    });
  }

  private handleData(payload: Uint8Array): void {
    const event = decodeVoiceEvent(payload);
    if (!event) return;
    if (event.type === "exercise-completed") {
      this.exerciseCompleted = true;
      void this.stopMicrophone();
      this.onStateChange("completed");
      this.onVoiceEvent(event);
      return;
    }
    if (event.type === "agent-state") {
      if (!this.exerciseCompleted) this.onStateChange(event.state);
      return;
    }
    this.onVoiceEvent(event);
  }
}
