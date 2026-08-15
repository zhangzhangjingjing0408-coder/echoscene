import { z } from "zod";

export const languageTagSchema = z
  .string()
  .min(2)
  .max(35)
  .regex(/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/, "Expected a BCP-47 language tag");

export const trainingStateSchema = z.enum([
  "idle",
  "preparing",
  "briefing",
  "prompting",
  "listening",
  "assessing",
  "probing",
  "rescue",
  "retry",
  "feedback",
  "completed",
  "error"
]);

export const transcriptSegmentSchema = z.object({
  id: z.string().min(1),
  text: z.string().min(1),
  language: languageTagSchema,
  startSeconds: z.number().nonnegative(),
  durationSeconds: z.number().positive()
});

export const evidenceReferenceSchema = z.object({
  segmentId: z.string().min(1),
  startSeconds: z.number().nonnegative(),
  label: z.string().min(1)
});

export const usefulVocabularySchema = z.object({
  term: z.string().min(1),
  meaningInContext: z.string().min(1),
  whyUseful: z.string().min(1),
  exampleUsage: z.string().min(1)
});

export const learningTaskSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["retell", "explain", "opinion"]),
  prompt: z.string().min(1),
  coachingFocus: z.string().min(1),
  requiredTerms: z.array(z.string()),
  usefulVocabulary: z.array(usefulVocabularySchema).default([]),
  evidence: z.array(evidenceReferenceSchema).min(1)
});

export const knowledgeUnitSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  summary: z.string().min(1),
  keywords: z.array(z.string()),
  evidence: z.array(evidenceReferenceSchema).min(1)
});

export const videoSummarySchema = z.object({
  overview: z.string().min(1),
  argumentStructure: z.array(z.string().min(1)).default([]),
  method: z.string().min(1),
  knowledgeUnits: z.array(knowledgeUnitSchema).min(3).max(5)
});

export const transcriptPreviewSchema = z.object({
  videoId: z.string().min(1),
  transcriptStatus: z.string().min(1),
  segments: z.array(transcriptSegmentSchema).min(1),
  cacheHit: z.boolean(),
  durationMs: z.number().nonnegative()
});

export const preparationDiagnosticsSchema = z.object({
  transcriptDurationMs: z.number().nonnegative(),
  contentDurationMs: z.number().nonnegative(),
  totalDurationMs: z.number().nonnegative(),
  transcriptCacheHit: z.boolean(),
  contentCacheHit: z.boolean(),
  transcriptSegmentCount: z.number().int().nonnegative().default(0),
  contentProvider: z.string().nullable().default(null),
  contentModel: z.string().nullable().default(null),
  promptVersion: z.string().nullable().default(null),
  providerRequestDurationMs: z.number().nonnegative().nullable().default(null),
  validationDurationMs: z.number().nonnegative().nullable().default(null),
  inputTokens: z.number().int().nonnegative().nullable().default(null),
  outputTokens: z.number().int().nonnegative().nullable().default(null),
  totalTokens: z.number().int().nonnegative().nullable().default(null),
  finishReason: z.string().nullable().default(null)
});

export const preparedLearningContextSchema = z.object({
  mode: z.enum(["demo", "grounded"]),
  videoId: z.string().min(1),
  transcriptStatus: z.string().min(1),
  segments: z.array(transcriptSegmentSchema).min(1),
  summary: videoSummarySchema,
  tasks: z.array(learningTaskSchema).min(3),
  diagnostics: preparationDiagnosticsSchema,
  task: learningTaskSchema
});

export const preparationStatusSchema = z.object({
  state: z.enum(["not-started", "running", "ready", "failed"]),
  result: preparedLearningContextSchema.nullable().default(null),
  errorCode: z.string().nullable().default(null),
  errorMessage: z.string().nullable().default(null),
  elapsedMs: z.number().nonnegative().default(0)
});

export const voiceControlEventSchema = z.object({
  schemaVersion: z.literal("1.0"),
  type: z.enum(["retry-response", "commit-turn"])
});

export const voiceSessionSchema = z.object({
  sessionId: z.string().uuid(),
  mode: z.enum(["demo", "live"]),
  livekitStatus: z.string().min(1),
  livekitToken: z.string().nullable(),
  livekitUrl: z.string().nullable(),
  agentName: z.string().nullable(),
  voiceModels: z.object({
    stt: z.string().min(1),
    llm: z.string().min(1),
    tts: z.string().min(1)
  })
});

export const voiceTrainingActionSchema = z.enum([
  "probe",
  "rescue",
  "retry",
  "complete"
]);

export const voiceRealtimeEventSchema = z.discriminatedUnion("type", [
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("transcript"),
    role: z.enum(["learner", "coach"]),
    text: z.string().min(1),
    isFinal: z.boolean(),
    language: z.string().optional()
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("session-record"),
    entries: z.array(z.object({
      role: z.enum(["learner", "coach"]),
      text: z.string().min(1),
      turnCount: z.number().int().positive()
    })).min(1)
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("agent-state"),
    agentState: z.enum(["initializing", "idle", "listening", "thinking", "speaking"]),
    trainingState: trainingStateSchema
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("training-action"),
    action: voiceTrainingActionSchema,
    trainingState: trainingStateSchema,
    turnCount: z.number().int().positive()
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("interruption"),
    trainingState: trainingStateSchema
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("latency"),
    phase: z.enum(["feedback-first-token", "feedback-complete"]),
    durationMs: z.number().nonnegative()
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("endpointing"),
    endOfUtteranceDelayMs: z.number().nonnegative(),
    transcriptionDelayMs: z.number().nonnegative()
  }),
  z.object({
    schemaVersion: z.literal("1.0"),
    type: z.literal("exercise-completed"),
    turnCount: z.number().int().positive(),
    maxTurns: z.number().int().positive()
  })
]);

export const trainingEventSchema = z.object({
  schemaVersion: z.literal("1.0"),
  id: z.string().uuid(),
  installationId: z.string().uuid(),
  sessionId: z.string().uuid(),
  occurredAt: z.string().datetime(),
  type: z.enum([
    "session.started",
    "content.prepared",
    "state.changed",
    "turn.started",
    "turn.completed",
    "interruption.detected",
    "feedback.generated",
    "session.completed",
    "error"
  ]),
  state: trainingStateSchema.optional(),
  durationMs: z.number().nonnegative().optional(),
  metadata: z.record(z.string(), z.unknown()).default({})
});

export type TrainingState = z.infer<typeof trainingStateSchema>;
export type TranscriptSegment = z.infer<typeof transcriptSegmentSchema>;
export type EvidenceReference = z.infer<typeof evidenceReferenceSchema>;
export type UsefulVocabulary = z.infer<typeof usefulVocabularySchema>;
export type LearningTask = z.infer<typeof learningTaskSchema>;
export type KnowledgeUnit = z.infer<typeof knowledgeUnitSchema>;
export type VideoSummary = z.infer<typeof videoSummarySchema>;
export type TranscriptPreview = z.infer<typeof transcriptPreviewSchema>;
export type PreparationDiagnostics = z.infer<typeof preparationDiagnosticsSchema>;
export type PreparedLearningContext = z.infer<typeof preparedLearningContextSchema>;
export type PreparationStatus = z.infer<typeof preparationStatusSchema>;
export type VoiceControlEvent = z.infer<typeof voiceControlEventSchema>;
export type VoiceSession = z.infer<typeof voiceSessionSchema>;
export type VoiceTrainingAction = z.infer<typeof voiceTrainingActionSchema>;
export type VoiceRealtimeEvent = z.infer<typeof voiceRealtimeEventSchema>;
export type TrainingEvent = z.infer<typeof trainingEventSchema>;

export interface YouTubePageContext {
  videoId: string | null;
  url: string;
  title: string;
  channel: string;
  currentTimeSeconds: number;
  theme: "light" | "dark";
  pageLanguage: string;
}
