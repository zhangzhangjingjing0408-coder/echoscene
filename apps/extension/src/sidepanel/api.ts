import {
  learningTaskSchema,
  preparationStatusSchema,
  type LearningTask,
  preparedLearningContextSchema,
  type PreparedLearningContext,
  type PreparationStatus,
  transcriptPreviewSchema,
  type TranscriptPreview,
  type VoiceSession,
  voiceSessionSchema,
  type YouTubePageContext
} from "@echoscene/contracts";

const API_BASE_URL = import.meta.env.VITE_ECHOSCENE_API_URL ?? "http://127.0.0.1:8787";

export class EchoSceneApiError extends Error {
  constructor(
    message: string,
    readonly code = "api_error",
    readonly retryable = false
  ) {
    super(message);
    this.name = "EchoSceneApiError";
  }
}

function prepareRequestBody(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string
) {
  return {
    installationId,
    youtubeUrl: context.url,
    videoId: context.videoId,
    title: context.title,
    channel: context.channel,
    contentLanguage: context.pageLanguage || "en",
    guidanceLanguage
  };
}

async function parseApiError(response: Response, fallback: string): Promise<EchoSceneApiError> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: { code?: string; message?: string; retryable?: boolean } | string;
  } | null;
  const detail = payload?.detail;
  const message =
    typeof detail === "object" && detail?.message
      ? detail.message
      : typeof detail === "string"
        ? detail
        : fallback;
  const code = typeof detail === "object" && detail?.code ? detail.code : "prepare_failed";
  const retryable = typeof detail === "object" && detail?.retryable === true;
  return new EchoSceneApiError(message, code, retryable);
}

export async function previewTranscript(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string
): Promise<TranscriptPreview> {
  if (!context.videoId) throw new EchoSceneApiError("The current page has no video ID.", "no_video");
  const response = await fetch(`${API_BASE_URL}/v1/videos/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prepareRequestBody(context, installationId, guidanceLanguage))
  }).catch(() => {
    throw new EchoSceneApiError(
      "EchoScene API is not reachable. Start the local API and try again.",
      "api_unreachable"
    );
  });
  if (!response.ok) throw await parseApiError(response, `Transcript failed (${response.status}).`);
  return transcriptPreviewSchema.parse(await response.json());
}

export async function translateTranscript(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string,
  targetLanguage = "zh-Hans"
): Promise<TranscriptPreview> {
  if (!context.videoId) throw new EchoSceneApiError("The current page has no video ID.", "no_video");
  const response = await fetch(`${API_BASE_URL}/v1/videos/transcript/translation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...prepareRequestBody(context, installationId, guidanceLanguage),
      targetLanguage
    })
  }).catch(() => {
    throw new EchoSceneApiError(
      "EchoScene API is not reachable. Start the local API and try again.",
      "api_unreachable"
    );
  });
  if (!response.ok) throw await parseApiError(response, `Translation failed (${response.status}).`);
  return transcriptPreviewSchema.parse(await response.json());
}

export async function getPreparationStatus(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string,
  restart = false
): Promise<PreparationStatus> {
  if (!context.videoId) throw new EchoSceneApiError("The current page has no video ID.", "no_video");
  const suffix = restart ? "?restart=true" : "";
  const response = await fetch(`${API_BASE_URL}/v1/videos/prepare/status${suffix}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prepareRequestBody(context, installationId, guidanceLanguage))
  }).catch(() => {
    throw new EchoSceneApiError(
      "EchoScene API is not reachable. Start the local API and try again.",
      "api_unreachable"
    );
  });
  if (!response.ok) {
    throw await parseApiError(response, `Preparation status failed (${response.status}).`);
  }
  return preparationStatusSchema.parse(await response.json());
}

export async function prepareVideoPreview(
  context: YouTubePageContext,
  installationId: string,
  guidanceLanguage: string
): Promise<PreparedLearningContext> {
  if (!context.videoId) throw new EchoSceneApiError("The current page has no video ID.", "no_video");
  const response = await fetch(`${API_BASE_URL}/v1/videos/prepare/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prepareRequestBody(context, installationId, guidanceLanguage))
  }).catch(() => {
    throw new EchoSceneApiError(
      "EchoScene API is not reachable. Start the local API and try again.",
      "api_unreachable"
    );
  });
  if (!response.ok) {
    throw await parseApiError(response, `Content preview failed (${response.status}).`);
  }
  return preparedLearningContextSchema.parse(await response.json());
}

export async function createVoiceSession(
  context: YouTubePageContext,
  prepared: PreparedLearningContext,
  task: LearningTask,
  installationId: string,
  guidanceLanguage: string
): Promise<VoiceSession> {
  const taskEvidenceIds = new Set(task.evidence.map((reference) => reference.segmentId));
  const linkedKnowledgeUnits = prepared.summary.knowledgeUnits
    .filter((unit) => unit.evidence.some((reference) => taskEvidenceIds.has(reference.segmentId)))
    .slice(0, 5);
  const response = await fetch(`${API_BASE_URL}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      installationId,
      videoId: context.videoId,
      guidanceLanguage,
      trainingLanguage: prepared.segments[0]?.language ?? "en",
      task: learningTaskSchema.parse(task),
      groundingContext: {
        schemaVersion: "1.0",
        videoThesis: prepared.summary.overview,
        knowledgeUnits: linkedKnowledgeUnits.map((unit) => ({
          title: unit.title,
          summary: unit.summary
        }))
      }
    })
  }).catch(() => {
    throw new EchoSceneApiError(
      "EchoScene API is not reachable. Start the local API and try again.",
      "api_unreachable"
    );
  });

  if (!response.ok) {
    throw new EchoSceneApiError(`Voice session failed (${response.status}).`, "voice_failed");
  }
  const session = voiceSessionSchema.parse(await response.json());
  if (!session.livekitToken || !session.livekitUrl || session.livekitStatus !== "ready") {
    throw new EchoSceneApiError("LiveKit Cloud is not configured.", "livekit_not_configured");
  }
  return session;
}
