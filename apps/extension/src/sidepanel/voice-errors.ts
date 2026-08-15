export type VoiceSetupErrorCode =
  | "microphone_permission_denied"
  | "microphone_not_found"
  | "microphone_in_use"
  | "microphone_unavailable"
  | "livekit_connection_failed";

export class VoiceSetupError extends Error {
  constructor(
    readonly code: VoiceSetupErrorCode,
    message: string,
    options?: ErrorOptions
  ) {
    super(message, options);
    this.name = "VoiceSetupError";
  }
}

export function classifyMicrophoneError(error: unknown): VoiceSetupErrorCode {
  const name = error instanceof Error
    ? error.name
    : typeof error === "object" && error !== null && "name" in error
      ? String(error.name)
      : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "microphone_permission_denied";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "microphone_not_found";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "microphone_in_use";
  }
  return "microphone_unavailable";
}

export async function requestMicrophoneAccess(
  mediaDevices: Pick<MediaDevices, "getUserMedia"> | undefined = navigator.mediaDevices
): Promise<void> {
  if (!mediaDevices?.getUserMedia) {
    throw new VoiceSetupError(
      "microphone_unavailable",
      "This browser context does not expose microphone capture."
    );
  }
  try {
    const stream = await mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    throw new VoiceSetupError(
      classifyMicrophoneError(error),
      "Chrome did not grant microphone access.",
      { cause: error }
    );
  }
}
