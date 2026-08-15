import type { VoiceConnectionState } from "./voice";

type CoachPortraitProps = {
  label: string;
  state: VoiceConnectionState | "complete";
};

export function CoachPortrait({ label, state }: CoachPortraitProps) {
  return (
    <div className="coach-portrait" data-state={state} role="img" aria-label={label}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle className="coach-backdrop" cx="60" cy="60" r="57" />
        <path className="coach-shoulders" d="M22 111c4-24 17-35 38-35s34 11 38 35" />
        <path className="coach-neck" d="M50 68v17c4 5 16 5 20 0V68" />
        <ellipse className="coach-face" cx="60" cy="49" rx="25" ry="31" />
        <path className="coach-hair" d="M35 48c-2-22 8-35 26-35 18 0 29 13 25 38-4-17-13-25-28-25-9 0-17 8-23 22Z" />
        <path className="coach-hair-side" d="M37 43c-4 21 0 34 8 41l5-14c-7-7-10-16-13-27Zm47-1c4 19 1 33-7 42l-6-14c7-7 10-16 13-28Z" />
        <path className="coach-eye" d="M47 49h5M68 49h5" />
        <path className="coach-brow" d="M45 43c3-2 7-2 10 0M65 43c3-2 7-2 10 0" />
        <path className="coach-nose" d="m60 50-2 10h4" />
        <path className="coach-mouth coach-mouth-rest" d="M54 66c4 2 8 2 12 0" />
        <ellipse className="coach-mouth coach-mouth-speak" cx="60" cy="67" rx="5" ry="3" />
      </svg>
      <span className="coach-state-dot" aria-hidden="true" />
    </div>
  );
}
