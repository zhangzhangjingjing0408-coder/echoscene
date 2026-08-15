import type {
  PreparedLearningContext,
  TranscriptPreview,
  TrainingState,
  YouTubePageContext
} from "@echoscene/contracts";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  createVoiceSession,
  EchoSceneApiError,
  getPreparationStatus,
  previewTranscript,
  translateTranscript
} from "./api";
import {
  clearDeepPracticeReady,
  getActiveYouTubeContext,
  getInstallationId,
  notifyDeepPracticeReady,
  openMicrophonePermissionPage,
  seekTo,
  trackDeepPreparation
} from "./chrome";
import { t, type GuideLanguage } from "./i18n";
import {
  loadCachedPreparation,
  loadCachedTranscript,
  loadCachedTranscriptTranslation,
  saveCachedPreparation,
  saveCachedTranscript,
  saveCachedTranscriptTranslation,
  takeReadyPreparation
} from "./preparation-cache";
import {
  deepPreparationCanUpgrade,
  transcriptSegmentsForDisplay
} from "./progressive-preparation";
import {
  filterTranscript,
  safeTranscriptFilename,
  transcriptAsSrt,
  transcriptAsText
} from "./transcript-study";
import { CoachPortrait } from "./CoachPortrait";
import { requestMicrophoneAccess, VoiceSetupError } from "./voice-errors";
import type {
  EchoSceneVoiceRoom,
  VoiceConnectionState,
  VoiceRoomEvent,
  VoiceTrainingAction,
  VoiceTranscriptEntry
} from "./voice";
import { mergeVoiceTranscript } from "./voice-transcript";
import {
  deleteCachedVoiceSession,
  loadCachedVoiceSession,
  saveCachedVoiceSession
} from "./voice-session-cache";
import {
  recordContentCompleted,
  recordExplicitTurnCommit,
  recordPracticeCompleted,
  recordVoiceEndpointing,
  recordVoiceLatency
} from "./telemetry";

type ViewState =
  | TrainingState
  | "context-error"
  | "prepare-error"
  | "summary"
  | "transcript-study"
  | "voice-connecting"
  | "voice-summary"
  | "voice-setup"
  | "voice-error";

const guideOptions = [
  { value: "zh-Hans", label: "中文引导" },
  { value: "en", label: "English guide" }
] satisfies Array<{ value: GuideLanguage; label: string }>;

function formatTime(seconds: number): string {
  const rounded = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(rounded / 60);
  return `${String(minutes).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}

export function App() {
  const [context, setContext] = useState<YouTubePageContext | null>(null);
  const [prepared, setPrepared] = useState<PreparedLearningContext | null>(null);
  const [transcriptPreview, setTranscriptPreview] = useState<TranscriptPreview | null>(null);
  const [restoredFromLocalCache, setRestoredFromLocalCache] = useState(false);
  const [view, setView] = useState<ViewState>("idle");
  const [guideLanguage, setGuideLanguage] = useState<GuideLanguage>("zh-Hans");
  const [installationId, setInstallationId] = useState<string>("");
  const [errorCode, setErrorCode] = useState<string>("");
  const [errorDetail, setErrorDetail] = useState<string>("");
  const [voiceState, setVoiceState] = useState<VoiceConnectionState>("disconnected");
  const [voiceAction, setVoiceAction] = useState<VoiceTrainingAction | null>(null);
  const [activeVoiceTurnCount, setActiveVoiceTurnCount] = useState(0);
  const [completedVoiceTurnCount, setCompletedVoiceTurnCount] = useState<number | null>(null);
  const [voiceTranscript, setVoiceTranscript] = useState<VoiceTranscriptEntry[]>([]);
  const [cachedVoiceTranscript, setCachedVoiceTranscript] = useState<VoiceTranscriptEntry[]>([]);
  const [interruptionCount, setInterruptionCount] = useState(0);
  const [voiceResponseDelayed, setVoiceResponseDelayed] = useState(false);
  const [turnCommitPending, setTurnCommitPending] = useState(false);
  const [taskIndex, setTaskIndex] = useState(0);
  const [deepPrepared, setDeepPrepared] = useState<PreparedLearningContext | null>(null);
  const [deepAnalysisState, setDeepAnalysisState] = useState<
    "idle" | "running" | "ready" | "failed"
  >("idle");
  const [showTranscript, setShowTranscript] = useState(false);
  const [transcriptQuery, setTranscriptQuery] = useState("");
  const [translatedTranscript, setTranslatedTranscript] = useState<TranscriptPreview | null>(null);
  const [translationState, setTranslationState] = useState<
    "idle" | "loading" | "ready" | "unavailable"
  >("idle");
  const [transcriptMode, setTranscriptMode] = useState<"original" | "translated">("original");
  const voiceRoomRef = useRef<EchoSceneVoiceRoom | null>(null);
  const voiceTranscriptRef = useRef<HTMLOListElement | null>(null);
  const preparationGenerationRef = useRef(0);
  const restorationKeyRef = useRef("");
  const practiceStartedRef = useRef(false);
  const voicePracticeStartedAtRef = useRef<number | null>(null);
  const voiceModelsRef = useRef<{ stt?: string; llm?: string; tts?: string }>({});
  const copy = t(guideLanguage);

  useEffect(() => {
    void getInstallationId().then(setInstallationId);
    void getActiveYouTubeContext()
      .then((nextContext) => {
        setContext(nextContext);
        document.documentElement.dataset.theme = nextContext.theme;
      })
      .catch(() => setView("context-error"));
  }, []);

  useEffect(() => () => {
    const room = voiceRoomRef.current;
    if (room) void room.disconnect();
  }, []);

  useEffect(() => {
    if (!context?.videoId || !installationId || view !== "idle") return;
    const restorationKey = `${context.videoId}.${guideLanguage}.${context.title}`;
    if (restorationKeyRef.current === restorationKey) return;
    restorationKeyRef.current = restorationKey;
    const generation = preparationGenerationRef.current;
    void (async () => {
      const cachedPreparation = await loadCachedPreparation(
        context.videoId!,
        guideLanguage,
        context.title
      );
      if (generation !== preparationGenerationRef.current) return;
      if (cachedPreparation) {
        void recordContentCompleted(cachedPreparation.diagnostics, true);
        setPrepared(cachedPreparation);
        setRestoredFromLocalCache(true);
        setDeepAnalysisState("ready");
        setView("summary");
        return;
      }
      const ready = await takeReadyPreparation(context.videoId!, guideLanguage);
      if (generation !== preparationGenerationRef.current) return;
      if (ready) {
        await saveCachedPreparation(context.title, guideLanguage, ready);
        void recordContentCompleted(ready.diagnostics);
        setPrepared(ready);
        setRestoredFromLocalCache(true);
        setDeepAnalysisState("ready");
        setView("summary");
        void clearDeepPracticeReady();
        return;
      }
      const cachedTranscript = await loadCachedTranscript(context.videoId!, context.title);
      if (!cachedTranscript || generation !== preparationGenerationRef.current) return;
      setTranscriptPreview(cachedTranscript);
      setView("transcript-study");
      setDeepAnalysisState("running");
      await trackDeepPreparation(context, installationId, guideLanguage);
      void pollDeepPreparation(context, generation);
    })();
  }, [context, guideLanguage, installationId, view]);

  useEffect(() => {
    if (view !== "listening") return;
    const transcript = voiceTranscriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [view, voiceTranscript]);

  useEffect(() => {
    const selectedTask = prepared?.tasks[taskIndex];
    if (!context?.videoId || !selectedTask) {
      setCachedVoiceTranscript([]);
      return;
    }
    let active = true;
    void loadCachedVoiceSession(context.videoId, selectedTask.id, guideLanguage).then((session) => {
      if (active) setCachedVoiceTranscript(session?.entries ?? []);
    });
    return () => { active = false; };
  }, [context?.videoId, guideLanguage, prepared, taskIndex]);

  useEffect(() => {
    if (!context?.videoId) return;
    let active = true;
    void loadCachedTranscriptTranslation(
      context.videoId,
      context.title,
      "zh-Hans"
    ).then((translation) => {
      if (!active || !translation) return;
      setTranslatedTranscript(translation);
      setTranslationState("ready");
    });
    return () => { active = false; };
  }, [context?.videoId, context?.title, guideLanguage]);

  useEffect(() => {
    if (view !== "listening" || (voiceState !== "thinking" && voiceState !== "response-error")) {
      setVoiceResponseDelayed(false);
      return;
    }
    if (voiceState === "response-error") {
      setVoiceResponseDelayed(true);
      return;
    }
    const timer = window.setTimeout(() => setVoiceResponseDelayed(true), 12_000);
    return () => window.clearTimeout(timer);
  }, [view, voiceState, voiceTranscript.length]);

  useEffect(() => {
    if (typeof chrome === "undefined" || !chrome.runtime?.onMessage) return;
    const listener = (message: { type?: string; context?: YouTubePageContext }) => {
      if (message.type === "PAGE_CONTEXT_CHANGED" && message.context) {
        const room = voiceRoomRef.current;
        if (room) void room.disconnect();
        voiceRoomRef.current = null;
        setContext(message.context);
        restorationKeyRef.current = "";
        preparationGenerationRef.current += 1;
        setPrepared(null);
        setTranscriptPreview(null);
        setRestoredFromLocalCache(false);
        setDeepAnalysisState("idle");
        setDeepPrepared(null);
        setShowTranscript(false);
        setTranscriptQuery("");
        setTranslatedTranscript(null);
        setTranslationState("idle");
        setTranscriptMode("original");
        setVoiceTranscript([]);
        setVoiceAction(null);
        setTurnCommitPending(false);
        setActiveVoiceTurnCount(0);
        setCompletedVoiceTurnCount(null);
        practiceStartedRef.current = false;
        setView("idle");
        document.documentElement.dataset.theme = message.context.theme;
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const shortInstallationId = useMemo(
    () => (installationId ? installationId.slice(0, 8) : "…"),
    [installationId]
  );
  const finalizedVoiceTranscript = useMemo(
    () => voiceTranscript.filter((entry) => entry.isFinal),
    [voiceTranscript]
  );
  const latestCoachCaption = useMemo(
    () => [...voiceTranscript].reverse().find((entry) => entry.role === "coach") ?? null,
    [voiceTranscript]
  );

  useEffect(() => {
    if (voiceState !== "completed" || !context?.videoId) return;
    const selectedTask = prepared?.tasks[taskIndex];
    if (!selectedTask || finalizedVoiceTranscript.length === 0) return;
    void saveCachedVoiceSession(
      context.videoId,
      selectedTask.id,
      guideLanguage,
      finalizedVoiceTranscript
    ).then((saved) => {
      if (saved) setCachedVoiceTranscript(saved.entries);
    });
  }, [
    context?.videoId,
    finalizedVoiceTranscript,
    guideLanguage,
    prepared,
    taskIndex,
    voiceState
  ]);

  async function preparePractice() {
    if (!context || !installationId) return;
    const generation = ++preparationGenerationRef.current;
    setView("preparing");
    setTranscriptPreview(null);
    setRestoredFromLocalCache(false);
    setDeepAnalysisState("idle");
    setDeepPrepared(null);
    setShowTranscript(false);
    setVoiceTranscript([]);
    setVoiceResponseDelayed(false);
    setVoiceAction(null);
    setTurnCommitPending(false);
    setActiveVoiceTurnCount(0);
    setCompletedVoiceTurnCount(null);
    practiceStartedRef.current = false;
    setErrorCode("");
    setErrorDetail("");
    try {
      const cached = await loadCachedPreparation(
        context.videoId!,
        guideLanguage,
        context.title
      );
      if (generation !== preparationGenerationRef.current) return;
      if (cached) {
        void recordContentCompleted(cached.diagnostics, true);
        setPrepared(cached);
        setRestoredFromLocalCache(true);
        setDeepAnalysisState("ready");
        setTaskIndex(0);
        setView("summary");
        return;
      }

      const transcript = await loadCachedTranscript(context.videoId!, context.title)
        ?? await previewTranscript(context, installationId, guideLanguage);
      if (generation !== preparationGenerationRef.current) return;
      setTranscriptPreview(transcript);
      await saveCachedTranscript(context.title, transcript);
      setShowTranscript(true);
      setView("transcript-study");
      setDeepAnalysisState("running");
      const ready = await takeReadyPreparation(context.videoId!, guideLanguage);
      if (ready) {
        await saveCachedPreparation(context.title, guideLanguage, ready);
        setDeepPrepared(ready);
        setDeepAnalysisState("ready");
        void recordContentCompleted(ready.diagnostics);
        void clearDeepPracticeReady();
        return;
      }
      await trackDeepPreparation(context, installationId, guideLanguage);

      void pollDeepPreparation(context, generation);
    } catch (error) {
      if (generation !== preparationGenerationRef.current) return;
      setPrepared(null);
      setErrorCode(error instanceof EchoSceneApiError ? error.code : "prepare_failed");
      setView("prepare-error");
    }
  }

  function changeGuideLanguage(nextLanguage: GuideLanguage) {
    const room = voiceRoomRef.current;
    if (room) void room.disconnect();
    voiceRoomRef.current = null;
    const generation = ++preparationGenerationRef.current;
    setGuideLanguage(nextLanguage);
    restorationKeyRef.current = "";
    setTranscriptPreview(null);
    setRestoredFromLocalCache(false);
    setDeepAnalysisState("idle");
    setDeepPrepared(null);
    setShowTranscript(false);
    setTranscriptQuery("");
    setTranslatedTranscript(null);
    setTranslationState("idle");
    setTranscriptMode("original");
    practiceStartedRef.current = false;
    setTaskIndex(0);
    setErrorCode("");
    setErrorDetail("");
    if (!context?.videoId) {
      setPrepared(null);
      setView("context-error");
      return;
    }
    void loadCachedPreparation(context.videoId, nextLanguage, context.title).then((cached) => {
      if (generation !== preparationGenerationRef.current) return;
      if (cached) {
        void recordContentCompleted(cached.diagnostics, true);
        setPrepared(cached);
        setRestoredFromLocalCache(true);
        setDeepAnalysisState("ready");
        setView("summary");
      } else {
        setPrepared(null);
        setView("idle");
      }
    });
  }

  function useDeepPractice() {
    if (!deepPrepared) return;
    void clearDeepPracticeReady();
    setPrepared(deepPrepared);
    setDeepPrepared(null);
    setTaskIndex(0);
    setVoiceTranscript([]);
    setVoiceAction(null);
    setTurnCommitPending(false);
    setView("summary");
  }

  async function pollDeepPreparation(
    activeContext: YouTubePageContext,
    generation: number,
    restart = false
  ) {
    let shouldRestart = restart;
    while (generation === preparationGenerationRef.current) {
      try {
        const status = await getPreparationStatus(
          activeContext,
          installationId,
          guideLanguage,
          shouldRestart
        );
        shouldRestart = false;
        if (status.state === "ready" && status.result) {
          const result = status.result;
          if (!deepPreparationCanUpgrade(
            result.videoId,
            activeContext.videoId,
            generation,
            preparationGenerationRef.current
          )) return;
          await saveCachedPreparation(activeContext.title, guideLanguage, result);
          void recordContentCompleted(result.diagnostics);
          await notifyDeepPracticeReady(activeContext.title);
          setDeepPrepared(result);
          setDeepAnalysisState("ready");
          return;
        }
        if (status.state === "failed") {
          setDeepAnalysisState("failed");
          setErrorCode(status.errorCode ?? "content_preparation_failed");
          setErrorDetail(status.errorMessage ?? "");
          return;
        }
        setDeepAnalysisState("running");
        await new Promise((resolve) => window.setTimeout(resolve, 3_000));
      } catch {
        if (generation === preparationGenerationRef.current) {
          setDeepAnalysisState("failed");
        }
        return;
      }
    }
  }

  async function retryDeepPreparation() {
    if (!context || !installationId || !transcriptPreview) return;
    const generation = preparationGenerationRef.current;
    setDeepAnalysisState("running");
    setErrorCode("");
    setErrorDetail("");
    await pollDeepPreparation(context, generation, true);
  }

  async function requestTranscriptTranslation() {
    if (!context || !installationId || translationState === "loading") return;
    if (translatedTranscript) {
      setTranscriptMode("translated");
      return;
    }
    setTranslationState("loading");
    try {
      const translation = await translateTranscript(
        context,
        installationId,
        guideLanguage,
        "zh-Hans"
      );
      await saveCachedTranscriptTranslation(context.title, "zh-Hans", translation);
      setTranslatedTranscript(translation);
      setTranscriptMode("translated");
      setTranslationState("ready");
    } catch {
      setTranslationState("unavailable");
    }
  }

  function downloadTranscript(format: "txt" | "srt") {
    if (!context) return;
    const originalSegments = transcriptPreview?.segments ?? prepared?.segments ?? [];
    const segments = transcriptMode === "translated" && translatedTranscript
      ? translatedTranscript.segments
      : originalSegments;
    if (!segments.length) return;
    const body = format === "srt" ? transcriptAsSrt(segments) : transcriptAsText(segments);
    const blob = new Blob([body], { type: format === "srt" ? "application/x-subrip" : "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeTranscriptFilename(context.title)}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function startVoicePractice() {
    if (!context || !prepared || !installationId) return;
    const selectedTask = prepared.tasks[taskIndex];
    if (!selectedTask) return;
    practiceStartedRef.current = true;
    setView("voice-connecting");
    setVoiceAction(null);
    setTurnCommitPending(false);
    setActiveVoiceTurnCount(0);
    setCompletedVoiceTurnCount(null);
    setVoiceTranscript([]);
    setInterruptionCount(0);
    setErrorCode("");
    try {
      // Request capture immediately from the button gesture, before token/network awaits.
      await requestMicrophoneAccess();
      const session = await createVoiceSession(
        context,
        prepared,
        selectedTask,
        installationId,
        guideLanguage
      );
      voiceModelsRef.current = session.voiceModels;
      const { EchoSceneVoiceRoom } = await import("./voice");
      const room = new EchoSceneVoiceRoom(setVoiceState, handleVoiceEvent);
      voiceRoomRef.current = room;
      await room.connect(session.livekitUrl!, session.livekitToken!);
      voicePracticeStartedAtRef.current = Date.now();
      setView("listening");
    } catch (error) {
      await voiceRoomRef.current?.disconnect().catch(() => undefined);
      voiceRoomRef.current = null;
      const code = error instanceof EchoSceneApiError || error instanceof VoiceSetupError
        ? error.code
        : "voice_failed";
      setErrorCode(code);
      setView(code === "livekit_not_configured" ? "voice-setup" : "voice-error");
    }
  }

  function handleVoiceEvent(event: VoiceRoomEvent) {
    if (event.type === "interruption") {
      setInterruptionCount((current) => current + 1);
      return;
    }
    if (event.type === "training-action") {
      setVoiceAction(event.action);
      setActiveVoiceTurnCount(event.turnCount);
      return;
    }
    if (event.type === "latency") {
      void recordVoiceLatency(event.phase, event.durationMs);
      return;
    }
    if (event.type === "endpointing") {
      void recordVoiceEndpointing(
        event.endOfUtteranceDelayMs,
        event.transcriptionDelayMs
      );
      return;
    }
    if (event.type === "session-record") {
      setVoiceTranscript(event.entries);
      return;
    }
    if (event.type === "exercise-completed") {
      setVoiceAction("complete");
      setActiveVoiceTurnCount(event.turnCount);
      setCompletedVoiceTurnCount(event.turnCount);
      setVoiceState("completed");
      return;
    }
    setVoiceTranscript((current) => mergeVoiceTranscript(current, event.entry));
  }

  async function finishVoicePractice() {
    try {
      await voiceRoomRef.current?.disconnect();
    } finally {
      voiceRoomRef.current = null;
      setVoiceState("disconnected");
      if (context?.videoId && task) {
        const saved = await saveCachedVoiceSession(
          context.videoId,
          task.id,
          guideLanguage,
          finalizedVoiceTranscript
        );
        if (saved) setCachedVoiceTranscript(saved.entries);
        const startedAt = voicePracticeStartedAtRef.current;
        if (startedAt !== null && finalizedVoiceTranscript.some((entry) => entry.role === "learner")) {
          void recordPracticeCompleted({
            taskKind: task.kind,
            durationMs: Math.max(0, Date.now() - startedAt),
            learnerTurnCount: completedVoiceTurnCount ?? activeVoiceTurnCount,
            coachTurnCount: finalizedVoiceTranscript.filter(
              (entry) => entry.role === "coach"
            ).length,
            retryCompleted: voiceAction === "complete",
            interruptionCount,
            llmModel: voiceModelsRef.current.llm ?? null,
            sttModel: voiceModelsRef.current.stt ?? null,
            ttsModel: voiceModelsRef.current.tts ?? null
          });
        }
      }
      voicePracticeStartedAtRef.current = null;
      setView("voice-summary");
    }
  }

  async function deleteVoicePracticeRecord() {
    if (!context?.videoId || !task) return;
    await deleteCachedVoiceSession(context.videoId, task.id, guideLanguage);
    setCachedVoiceTranscript([]);
  }

  async function resumeVoiceAudio() {
    try {
      await voiceRoomRef.current?.resumeAudio();
    } catch {
      setErrorCode("audio_playback_blocked");
      setView("voice-error");
    }
  }

  async function retryCoachResponse() {
    setVoiceResponseDelayed(false);
    try {
      await voiceRoomRef.current?.requestCoachResponse();
    } catch {
      setVoiceResponseDelayed(true);
    }
  }

  async function commitCurrentVoiceTurn() {
    if (turnCommitPending || voiceState !== "listening") return;
    setTurnCommitPending(true);
    try {
      await voiceRoomRef.current?.commitUserTurn();
      void recordExplicitTurnCommit();
    } catch {
      setVoiceResponseDelayed(true);
    } finally {
      window.setTimeout(() => setTurnCommitPending(false), 2_000);
    }
  }

  function beginPracticePath() {
    practiceStartedRef.current = true;
    setTaskIndex(0);
    setView("briefing");
  }

  const isWorking = view === "preparing" || view === "assessing";
  const task = prepared?.tasks[taskIndex];
  const isProgressivePreview = false;
  const taskCount = prepared?.tasks.length ?? 0;
  const visibleTranscriptSegments = transcriptSegmentsForDisplay(
    transcriptPreview?.segments,
    prepared?.segments
  );
  const originalStudySegments = transcriptPreview?.segments ?? prepared?.segments ?? [];
  const studySegments = transcriptMode === "translated" && translatedTranscript
    ? translatedTranscript.segments
    : originalStudySegments;
  const filteredStudySegments = filterTranscript(studySegments, transcriptQuery);
  const evidence = task?.evidence[0];
  const transcriptErrorCopy: Partial<Record<string, string>> = {
    transcript_no_track: copy.transcriptNoTrack,
    transcript_request_blocked: copy.transcriptTemporary,
    transcript_temporarily_unavailable: copy.transcriptTemporary,
    transcript_access_restricted: copy.transcriptRestricted,
    transcript_provider_auth: copy.transcriptProviderSetup,
    transcript_provider_not_configured: copy.transcriptProviderSetup
  };
  const deepErrorCopy: Partial<Record<string, string>> = {
    content_provider_timeout: copy.deepTimeout,
    content_provider_auth: copy.deepAuth,
    content_provider_balance: copy.deepBalance,
    content_provider_rate_limited: copy.deepRateLimited,
    content_provider_network: copy.deepNetwork,
    content_provider_temporarily_unavailable: copy.deepTemporary,
    content_provider_rejected: copy.deepRejected,
    content_json_invalid: copy.deepJsonInvalid,
    content_output_truncated: copy.deepTruncated,
    content_output_empty: copy.deepEmpty,
    content_output_filtered: copy.deepFiltered,
    content_provider_capacity: copy.deepCapacity,
    content_response_shape_invalid: copy.deepSchema,
    content_schema_validation_failed: copy.deepSchema,
    content_evidence_validation_failed: copy.deepEvidence,
    content_preparation_failed: copy.deepValidation
  };
  const errorLead = errorCode === "api_unreachable"
    ? copy.apiUnavailable
    : transcriptErrorCopy[errorCode] ?? copy.sourceUnavailable;
  const voiceStatus = voiceState === "thinking"
    ? copy.voiceThinking
    : voiceState === "response-error"
      ? copy.voiceResponseError
    : voiceState === "completed"
      ? copy.voiceCompleted
    : voiceState === "speaking"
      ? copy.voiceSpeaking
      : voiceState === "listening"
        ? copy.voiceListening
        : voiceState === "audio-blocked"
          ? copy.voiceAudioBlocked
          : voiceState === "agent-timeout"
            ? copy.voiceAgentTimeout
        : voiceState === "agent-present"
          ? copy.agentPresent
          : copy.microphoneConnected;
  const voiceErrorCopy: Partial<Record<string, string>> = {
    microphone_permission_denied: copy.microphonePermissionDenied,
    microphone_not_found: copy.microphoneNotFound,
    microphone_in_use: copy.microphoneInUse,
    microphone_unavailable: copy.microphoneUnavailable,
    livekit_connection_failed: copy.livekitConnectionFailed,
    api_unreachable: copy.apiUnavailable
  };

  function renderTranscriptWorkspace(compact = false) {
    return (
      <div className={compact ? "transcript-workspace is-compact" : "transcript-workspace"}>
        <div className="transcript-toolbar">
          <label className="transcript-search">
            <span>{copy.searchTranscript}</span>
            <input
              type="search"
              value={transcriptQuery}
              onChange={(event) => setTranscriptQuery(event.target.value)}
              placeholder={copy.searchTranscriptPlaceholder}
            />
          </label>
          <div className="transcript-mode" aria-label={copy.transcriptLanguage}>
            <button
              type="button"
              aria-pressed={transcriptMode === "original"}
              onClick={() => setTranscriptMode("original")}
            >{copy.originalTranscript}</button>
            <button
              type="button"
              aria-pressed={transcriptMode === "translated"}
              disabled={translationState === "loading"}
              onClick={() => void requestTranscriptTranslation()}
            >{translationState === "loading" ? copy.translatingTranscript : copy.chineseTranscript}</button>
          </div>
          {translationState === "unavailable" && (
            <p className="translation-note" role="status">{copy.translationUnavailable}</p>
          )}
          <div className="transcript-export" aria-label={copy.exportTranscript}>
            <button type="button" onClick={() => downloadTranscript("txt")}>TXT</button>
            <button type="button" onClick={() => downloadTranscript("srt")}>SRT</button>
          </div>
        </div>
        <ol className="transcript-scroll study-scroll" tabIndex={0} aria-label={copy.fullTranscript}>
          {filteredStudySegments.map((segment) => (
            <li key={`${transcriptMode}-${segment.id}`}>
              <button
                type="button"
                onClick={() => void seekTo(segment.startSeconds)}
                aria-label={`${copy.jumpTo} ${formatTime(segment.startSeconds)}`}
              >{formatTime(segment.startSeconds)}</button>
              <p>{segment.text}</p>
            </li>
          ))}
        </ol>
        {!filteredStudySegments.length && (
          <p className="no-search-result">{copy.noTranscriptMatches}</p>
        )}
      </div>
    );
  }

  return (
    <main className="shell" aria-busy={isWorking}>
      <header className="masthead">
        <div className="wordmark" aria-label="EchoScene">
          <span className="echo-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>EchoScene</span>
        </div>
        <span className="mode-label">{copy.beta}</span>
      </header>

      <section className="source" aria-labelledby="source-heading">
        <p className="eyebrow" id="source-heading">{copy.currentSource}</p>
        {context ? (
          <>
            <h1>{context.title}</h1>
            <p className="source-meta">{context.channel} · YouTube</p>
          </>
        ) : view === "context-error" ? (
          <div className="empty-state">
            <h1>{copy.openYouTube}</h1>
            <p>{copy.openYouTubeBody}</p>
          </div>
        ) : (
          <div className="source-skeleton" aria-label={copy.reading} />
        )}
      </section>

      {view === "idle" && context && (
        <section className="opening stage-enter">
          <p className="opening-line">{copy.openingLine}</p>
          <ol className="compact-path" aria-label={copy.pathLabel}>
            <li><span>01</span>{copy.path1}</li>
            <li><span>02</span>{copy.path2}</li>
            <li><span>03</span>{copy.path3}</li>
          </ol>
          <button
            className="primary-action"
            type="button"
            onClick={() => void preparePractice()}
            disabled={!installationId}
          >
            {copy.prepare}<span aria-hidden="true">↗</span>
          </button>
          <p className="demo-note">{copy.groundedNote}</p>
        </section>
      )}

      {view === "preparing" && (
        <section className="working stage-enter" aria-live="polite">
          <div className="working-index">{transcriptPreview ? "02—03" : "01—03"}</div>
          <h2>{transcriptPreview ? copy.organizing : copy.reading}</h2>
          <p>{transcriptPreview ? copy.organizingBody : copy.readingBody}</p>
          {transcriptPreview && (
            <div className="transcript-preview">
              <div className="section-heading">
                <p className="eyebrow">{copy.transcriptReady}</p>
                <span className="ready-dot">{transcriptPreview.segments.length}</span>
              </div>
              <ol className="transcript-scroll" tabIndex={0} aria-label={copy.fullTranscript}>
                {transcriptPreview.segments.map((segment) => (
                  <li key={segment.id}>
                    <button
                      type="button"
                      onClick={() => void seekTo(segment.startSeconds)}
                      aria-label={`${copy.jumpTo} ${formatTime(segment.startSeconds)}`}
                    >
                      {formatTime(segment.startSeconds)}
                    </button>
                    <p>{segment.text}</p>
                  </li>
                ))}
              </ol>
              <small>{copy.semanticStillRunning}</small>
            </div>
          )}
          <div className="quiet-progress"><span /></div>
        </section>
      )}

      {view === "transcript-study" && transcriptPreview && (
        <section className="transcript-study stage-enter">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{copy.transcriptStudyLabel}</p>
              <h2>{copy.transcriptStudyTitle}</h2>
            </div>
            <span className="ready-dot">{studySegments.length}</span>
          </div>
          <p className="transcript-study-intro">{copy.transcriptStudyBody}</p>

          {deepAnalysisState === "running" && (
            <div className="deep-status is-running" role="status">
              <span aria-hidden="true" />
              <div><strong>{copy.deepRunningTitle}</strong><p>{copy.deepStudyRunning}</p></div>
            </div>
          )}
          {deepAnalysisState === "failed" && (
            <div className="deep-status is-failed" role="alert">
              <div><strong>{copy.deepFailedTitle}</strong><p>{deepErrorCopy[errorCode] ?? copy.deepStudyFailed}</p></div>
              {errorDetail && <small className="deep-error-detail">{errorDetail}</small>}
              <button type="button" onClick={() => void retryDeepPreparation()}>{copy.retryDeepAnalysis}</button>
            </div>
          )}
          {deepPrepared && (
            <div className="deep-ready" role="status">
              <p className="eyebrow">{copy.deepReadyLabel}</p>
              <strong>{copy.deepReadyTitle}</strong>
              <p>{copy.deepStudyReady}</p>
              <button className="primary-action" type="button" onClick={useDeepPractice}>
                {copy.openDeepPractice}<span aria-hidden="true">↗</span>
              </button>
            </div>
          )}

          {renderTranscriptWorkspace()}
        </section>
      )}

      {view === "prepare-error" && (
        <section className="feedback stage-enter" role="alert">
          <p className="eyebrow">{copy.prepareError}</p>
          <h2>{errorLead}</h2>
          <p className="feedback-body">{copy.errorBody}</p>
          <button className="primary-action" type="button" onClick={() => void preparePractice()}>
            {copy.retryPrepare}<span aria-hidden="true">↗</span>
          </button>
        </section>
      )}

      {view === "summary" && prepared && (
        <section className="summary-stage stage-enter">
          {visibleTranscriptSegments.length > 0 && (
            <div className="transcript-disclosure">
              <button
                className="transcript-toggle"
                type="button"
                aria-expanded={showTranscript}
                onClick={() => setShowTranscript((current) => !current)}
              >
                <span>{copy.fullTranscript}</span>
                <small>{visibleTranscriptSegments.length}</small>
                <span aria-hidden="true">{showTranscript ? "−" : "+"}</span>
              </button>
              {showTranscript && renderTranscriptWorkspace(true)}
            </div>
          )}
          <div className="section-heading">
            <p className="eyebrow">
              {isProgressivePreview ? copy.previewLabel : copy.summaryLabel}
            </p>
            <span className="ready-dot">{prepared.summary.knowledgeUnits.length}</span>
          </div>
          <h2>{prepared.summary.overview}</h2>
          <p className="summary-method">
            {isProgressivePreview
              ? copy.progressivePreviewMethod
              : prepared.summary.method.startsWith("semantic-content-")
              ? copy.semanticSummaryMethod
              : copy.extractiveSummaryMethod}
          </p>

          {isProgressivePreview && deepAnalysisState === "running" && (
            <div className="deep-status is-running" role="status">
              <span aria-hidden="true" />
              <div><strong>{copy.deepRunningTitle}</strong><p>{copy.deepAnalysisRunning}</p></div>
            </div>
          )}
          {isProgressivePreview && deepAnalysisState === "failed" && (
            <div className="deep-status is-failed" role="alert">
              <div><strong>{copy.deepFailedTitle}</strong><p>{copy.deepAnalysisFailed}</p></div>
              <button type="button" onClick={() => void retryDeepPreparation()}>{copy.retryDeepAnalysis}</button>
            </div>
          )}
          {deepPrepared && (
            <div className="deep-ready" role="status">
              <p className="eyebrow">{copy.deepReadyLabel}</p>
              <strong>{copy.deepReadyTitle}</strong>
              <p>{copy.deepReadyBody}</p>
              <button className="primary-action" type="button" onClick={useDeepPractice}>
                {copy.openDeepPractice}<span aria-hidden="true">↗</span>
              </button>
            </div>
          )}

          {prepared.summary.argumentStructure.length > 0 && (
            <div className="argument-map" aria-label={copy.argumentStructure}>
              <p className="eyebrow">{copy.argumentStructure}</p>
              <ol>
                {prepared.summary.argumentStructure.map((step, index) => (
                  <li key={`${index}-${step}`}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p>{step}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="knowledge-map" aria-label={copy.knowledgeMap}>
            <p className="eyebrow">
              {isProgressivePreview ? copy.previewSourceMoments : copy.knowledgeMap}
            </p>
            <ol>
              {prepared.summary.knowledgeUnits.map((unit, index) => (
                <li key={unit.id}>
                  <button
                    type="button"
                    onClick={() => void seekTo(unit.evidence[0].startSeconds)}
                  >
                    <span>{formatTime(unit.evidence[0].startSeconds)}</span>
                    <strong>{index + 1}. {unit.title}</strong>
                    <small>{unit.summary}</small>
                  </button>
                </li>
              ))}
            </ol>
          </div>

          <button className="primary-action" type="button" onClick={beginPracticePath}>
            {copy.beginPath}<span aria-hidden="true">↗</span>
          </button>
          <p className="provider-note">{copy.sourceProvider}: {prepared.transcriptStatus}</p>
          <p className="provider-note">
            {restoredFromLocalCache || prepared.diagnostics.contentCacheHit ? copy.cacheHit : copy.generatedFresh} · {copy.elapsed} {Math.max(1, Math.round(prepared.diagnostics.totalDurationMs / 1000))}s
          </p>
        </section>
      )}

      {view === "briefing" && task && evidence && (
        <section className="task stage-enter">
          <div className="section-heading">
            <p className="eyebrow">
              {isProgressivePreview ? copy.warmupQuestion : copy.question} {taskIndex + 1} {copy.of} {taskCount} · {copy[task.kind]}
            </p>
            <span className="ready-dot">{copy.duration}</span>
          </div>
          <h2>{task.prompt}</h2>
          <p className="focus-copy">{task.coachingFocus}</p>

          <button
            className="evidence-link"
            type="button"
            onClick={() => void seekTo(evidence.startSeconds)}
          >
            <span>{formatTime(evidence.startSeconds)}</span>
            {evidence.label}
          </button>

          <div className="term-line" aria-label={copy.usefulTerms}>
            <span>{copy.usefulTerms}</span>
            {task.usefulVocabulary.length > 0 ? (
              <ul>
                {task.usefulVocabulary.map((item) => (
                  <li key={item.term}>
                    <strong>{item.term}</strong>
                    <p>{item.meaningInContext} · {item.whyUseful}</p>
                    <small>{item.exampleUsage}</small>
                  </li>
                ))}
              </ul>
            ) : (
              <p>{task.requiredTerms.length ? task.requiredTerms.join(" · ") : copy.noTerms}</p>
            )}
          </div>

          {studySegments.length > 0 && (
            <details className="reference-transcript">
              <summary>{copy.fullTranscript}</summary>
              {renderTranscriptWorkspace(true)}
            </details>
          )}

          {cachedVoiceTranscript.length > 0 && (
            <details className="previous-practice">
              <summary>{copy.previousPractice}</summary>
              <ol className="voice-transcript session-transcript">
                {cachedVoiceTranscript.map((entry) => (
                  <li key={entry.id} className={entry.role}>
                    <span>{entry.role === "learner" ? copy.you : copy.coach}</span>
                    <p>{entry.text}</p>
                  </li>
                ))}
              </ol>
              <button type="button" onClick={() => void deleteVoicePracticeRecord()}>
                {copy.deletePracticeRecord}
              </button>
            </details>
          )}

          <button className="speak-action" type="button" onClick={() => void startVoicePractice()}>
            <span className="mic-glyph" aria-hidden="true">●</span>
            {copy.startSpeaking}
          </button>
          <div className="task-navigation">
            <button type="button" onClick={() => setView("summary")}>{copy.backToSummary}</button>
            {taskIndex > 0 && (
              <button type="button" onClick={() => setTaskIndex(taskIndex - 1)}>{copy.previousTask}</button>
            )}
            {prepared && taskIndex < taskCount - 1 && (
              <button type="button" onClick={() => setTaskIndex(taskIndex + 1)}>{copy.nextTask}</button>
            )}
          </div>
        </section>
      )}

      {view === "voice-connecting" && (
        <section className="working stage-enter" aria-live="polite">
          {task && (
            <div className="voice-task-anchor">
              <span>{copy.currentQuestion} · {taskIndex + 1}</span>
              <p>{task.prompt}</p>
            </div>
          )}
          <div className="working-index">LIVEKIT</div>
          <h2>{copy.connecting}</h2>
          <p>{copy.connectingBody}</p>
          <div className="quiet-progress"><span /></div>
        </section>
      )}

      {view === "listening" && (
        <section className="voice-stage stage-enter">
          {task && (
            <div className="voice-task-anchor">
              <span>{isProgressivePreview ? copy.warmupQuestion : copy.currentQuestion} · {taskIndex + 1} {copy.of} {taskCount}</span>
              <p>{task.prompt}</p>
            </div>
          )}
          {prepared && (
            <details className="voice-context" open>
              <summary>{copy.deepContextDuringPractice}</summary>
              {task && <p className="voice-coaching-focus">{task.coachingFocus}</p>}
              <p>{prepared.summary.overview}</p>
              <ol>
                {prepared.summary.knowledgeUnits.map((unit) => (
                  <li key={unit.id}>
                    <strong>{unit.title}</strong>
                    <span>{unit.summary}</span>
                  </li>
                ))}
              </ol>
              {task && task.usefulVocabulary.length > 0 && (
                <div className="voice-vocabulary">
                  <strong>{copy.usefulTerms}</strong>
                  {task.usefulVocabulary.slice(0, 4).map((item) => (
                    <p key={item.term}><b>{item.term}</b> · {item.meaningInContext}</p>
                  ))}
                </div>
              )}
            </details>
          )}
          {studySegments.length > 0 && (
            <details className="reference-transcript voice-transcript-reference">
              <summary>{copy.fullTranscript}</summary>
              {renderTranscriptWorkspace(true)}
            </details>
          )}
          <div className="coach-stage" aria-live="polite">
            <CoachPortrait label={copy.coachPortraitLabel} state={voiceState} />
            <div>
              <p className="eyebrow">{copy.coachName} · {copy.livePractice}</p>
              <h2>{voiceStatus}</h2>
              <p>{voiceState === "completed"
                ? copy.voiceCompletedBody
                : voiceState === "connected" || voiceState === "agent-timeout"
                  ? copy.waitingForAgent
                  : copy.agentPresentBody}</p>
            </div>
          </div>
          <p className="voice-round-progress">
            {completedVoiceTurnCount === null
              ? `${copy.voiceRoundProgress} ${activeVoiceTurnCount} / 4`
              : `${copy.voiceCompletedAtRound} ${completedVoiceTurnCount}`}
          </p>
          {voiceState === "listening" && (
            <button
              className="commit-turn-action"
              type="button"
              disabled={turnCommitPending}
              onClick={() => void commitCurrentVoiceTurn()}
            >
              {turnCommitPending ? copy.committingAnswer : copy.finishAnswer}
            </button>
          )}
          <div className="coach-live-caption" aria-live="polite" aria-atomic="true">
            <span>{copy.coachLiveCaption}</span>
            <p>{latestCoachCaption
              ? `${latestCoachCaption.text}${latestCoachCaption.isFinal ? "" : " …"}`
              : copy.coachCaptionWaiting}</p>
          </div>
          {voiceState === "audio-blocked" && (
            <button className="audio-unlock-action" type="button" onClick={() => void resumeVoiceAudio()}>
              {copy.enableVoiceAudio}
            </button>
          )}
          {voiceAction && (
            <p className={`voice-action action-${voiceAction}`}>
              {copy[`voiceAction_${voiceAction}`]}
            </p>
          )}
          {voiceResponseDelayed && (
            <div className="voice-delay" role="alert">
              <p>{copy.voiceTakingLong}</p>
              <button type="button" onClick={() => void retryCoachResponse()}>
                {copy.retryCoachResponse}
              </button>
            </div>
          )}
          {interruptionCount > 0 && (
            <p className="interruption-note">{copy.interruptionHandled}</p>
          )}
          <div className="conversation-heading">
            <p className="eyebrow">{copy.liveTranscript}</p>
            <span>{finalizedVoiceTranscript.length}</span>
          </div>
          <ol
            ref={voiceTranscriptRef}
            className="voice-transcript"
            aria-label={copy.liveTranscript}
            aria-live="polite"
            aria-relevant="additions text"
          >
            {voiceTranscript.length ? voiceTranscript.map((entry) => (
              <li key={entry.id} className={entry.role}>
                <span>{entry.role === "learner" ? copy.you : copy.coach}</span>
                <p>{entry.text}{!entry.isFinal ? " …" : ""}</p>
              </li>
            )) : (
              <li className="empty-transcript"><p>{copy.transcriptWaiting}</p></li>
            )}
          </ol>
          <button className="finish-action" type="button" onClick={() => void finishVoicePractice()}>
            {voiceAction === "complete" ? copy.reviewSession : copy.finishVoice}
          </button>
        </section>
      )}

      {view === "voice-summary" && task && (
        <section className="voice-summary stage-enter">
          <div className="session-heading">
            <CoachPortrait label={copy.coachPortraitLabel} state="complete" />
            <div>
              <p className="eyebrow">{copy.sessionRecord}</p>
              <h2>{copy.sessionComplete}</h2>
            </div>
          </div>
          <div className="session-question">
            <span>{copy.practicedQuestion}</span>
            <p>{task.prompt}</p>
          </div>
          <p className="session-note">{copy.sessionRecordBody}</p>
          {completedVoiceTurnCount !== null && (
            <p className="session-round-summary">
              {copy.voiceSessionRoundSummary} {completedVoiceTurnCount}
            </p>
          )}
          <p className="local-record-note">{copy.localSessionOnly}</p>
          <ol className="voice-transcript session-transcript" aria-label={copy.sessionRecord}>
            {finalizedVoiceTranscript.length ? finalizedVoiceTranscript.map((entry) => (
              <li key={entry.id} className={entry.role}>
                <span>{entry.role === "learner" ? copy.you : copy.coach}</span>
                <p>{entry.text}</p>
              </li>
            )) : (
              <li className="empty-transcript"><p>{copy.noSessionRecord}</p></li>
            )}
          </ol>
          <button className="primary-action" type="button" onClick={() => setView("briefing")}>
            {copy.backToTask}<span aria-hidden="true">↗</span>
          </button>
          {deepPrepared && (
            <div className="deep-ready session-upgrade" role="status">
              <p className="eyebrow">{copy.deepReadyLabel}</p>
              <strong>{copy.deepReadyTitle}</strong>
              <p>{copy.deepReadyBody}</p>
              <button className="primary-action" type="button" onClick={useDeepPractice}>
                {copy.openDeepPractice}<span aria-hidden="true">↗</span>
              </button>
            </div>
          )}
          {!deepPrepared && isProgressivePreview && deepAnalysisState === "running" && (
            <div className="deep-status is-running session-upgrade" role="status">
              <span aria-hidden="true" />
              <div><strong>{copy.deepRunningTitle}</strong><p>{copy.deepSessionWaiting}</p></div>
            </div>
          )}
          {!isProgressivePreview && prepared && taskIndex < taskCount - 1 && (
            <button
              className="finish-action"
              type="button"
              onClick={() => {
                setTaskIndex((current) => current + 1);
                setView("briefing");
              }}
            >
              {copy.nextTask}
            </button>
          )}
        </section>
      )}

      {view === "voice-setup" && (
        <section className="voice-stage stage-enter" role="status">
          <p className="eyebrow">{copy.listening}</p>
          <div className="voice-status-mark" aria-hidden="true"><span /></div>
          <h2>{copy.voiceNeedsSetup}</h2>
          <p>{copy.voiceNeedsSetupBody}</p>
          <button className="finish-action" type="button" onClick={() => setView("briefing")}>
            {copy.backToTask}
          </button>
        </section>
      )}

      {view === "voice-error" && (
        <section className="voice-stage stage-enter" role="alert">
          <p className="eyebrow">{copy.voiceError}</p>
          <div className="voice-status-mark" aria-hidden="true"><span /></div>
          <h2>{copy.voiceError}</h2>
          <p>{voiceErrorCopy[errorCode] ?? copy.microphoneError}</p>
          {errorCode === "microphone_permission_denied" && (
            <button
              className="audio-unlock-action"
              type="button"
              onClick={() => void openMicrophonePermissionPage()}
            >
              {copy.openMicrophonePermissionPage}
            </button>
          )}
          <button className="finish-action" type="button" onClick={() => setView("briefing")}>
            {copy.backToTask}
          </button>
        </section>
      )}

      <footer className="footer">
        <label>
          <span>{copy.guide}</span>
          <select
            value={guideLanguage}
            onChange={(event) => changeGuideLanguage(event.target.value as GuideLanguage)}
          >
            {guideOptions.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <span title={installationId}>{copy.anonymous} · {shortInstallationId}</span>
      </footer>
    </main>
  );
}
