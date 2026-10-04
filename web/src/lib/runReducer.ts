// Pure reducer for the SSE event stream (CONTRACTS §6.1). Applied by Run.tsx and Chat.tsx as
// events arrive; also the unit under test for "idempotent by id / ordering / verdict revisions".
//
// Idempotency: EventSource replays everything after a reconnect (Last-Event-ID), so every event
// must be a no-op the second time it arrives. Ordering: `plan` and `verdict` carry their own
// `revision`, so an event that arrives out of order can never regress a newer one.

export interface SourceInfo {
  id: string | null;
  as_on: string | null;
}

// 'reasoning' (product update, Oct 2026): the AI-review step of a check run, between the instant
// rule-based verdict (revision 1) and a possible reviewed verdict (revision 2, `ai_reviewed`).
// 'reading_image' (agent harness, Oct 2026): a screenshot is being read by OCR + a local vision
// model, before extraction proper starts; only appears when the check included an image.
export type Stage =
  | 'received'
  | 'reading_image'
  | 'extracting'
  | 'planning'
  | 'executing'
  | 'scoring'
  | 'reasoning'
  | 'explaining'
  | 'answering';
export interface StageEvent {
  stage: Stage;
  t_ms: number;
}

/** `image_reading` (agent harness): what the vision model saw in an uploaded screenshot. */
export interface ImageReadingEvent {
  screen: string;
  description: string;
  cues: string[];
}

export interface EntityItem {
  id: string;
  type: string;
  cls: string;
  display: string;
  origin: string;
}
export interface EntitiesEvent {
  items: EntityItem[];
}

export type StepStatus = 'pending' | 'running' | 'done' | 'unknown' | 'skipped';
export interface PlanStepWire {
  id: string;
  checker_id: string;
  family: string;
  status: StepStatus;
}
export interface PlanEvent {
  revision: number;
  steps: PlanStepWire[];
}

export type ResultStatus = 'hit' | 'clear' | 'unknown' | 'error' | 'skipped';
/** What was checked and what came back (satark/harness/proof.py); text is already in the user's language. */
export interface Proof {
  checked: string;
  source_name: string;
  as_on?: string | null;
  live?: boolean;
  fetched_at?: string;
  result: string;
  outcome: 'found' | 'clear' | 'warning' | 'unknown';
  why?: string | null;
  url?: string | null;
  items?: { title: string; url: string }[];
}
export interface CheckResultEvent {
  proof?: Proof;
  step_id: string;
  checker_id: string;
  family: string;
  status: ResultStatus;
  signals: string[];
  source: SourceInfo;
  stale: boolean;
  cached: boolean;
}

export type Level = 'HIGH_RISK' | 'SUSPICIOUS' | 'NO_SIGNS' | 'UNKNOWN';
export type Confidence = 'SURE' | 'FAIRLY_SURE' | 'NOT_SURE';
export interface VerdictReason {
  code: string;
  weight: string;
  title: string;
  source: SourceInfo;
}
export interface FamilyCheckedWire {
  family: string;
  status: 'done' | 'unknown' | 'skipped';
}
export interface VerdictEvent {
  revision: number;
  level: Level;
  confidence: Confidence;
  reasons: VerdictReason[];
  worth_noting: string[];
  assurances: string[];
  actions: string[];
  scam_type?: string | null;
  /** The text describes a known scam (news, awareness) and asks nothing of the reader. */
  about_scam?: boolean;
  simulator?: string | null;
  sim_params?: { rate: number; period: 'day' | 'week' | 'month' } | null;
  lesson?: string | null;
  checked: FamilyCheckedWire[];
  scoring_version: string;
  /** True once the AI review pass (not just the instant rule-based score) has run this revision.
   * Absent/false for every run until the agent harness lands - the card then shows no badge. */
  ai_reviewed?: boolean;
}

export interface ExplanationEvent {
  summary: string;
  reasons: { code: string; text: string }[];
  chips: string[];
  fallback_used: boolean;
  lang: string;
}

export interface AskUserEvent {
  question_id: string;
  text: string;
  options: { id: string; label: string }[];
}

/** `agent_step`: one iteration of the model's tool-use loop (up to 3 per run). `thought` is a
 * short model sentence (<=160 chars) and may be empty. */
export interface AgentAction {
  tool: string;
  label: string;
}
export interface AgentStepEvent {
  step: number;
  thought: string;
  actions: AgentAction[];
}

export interface ToolStatusEvent {
  tool: string;
  status: 'start' | 'end';
  /** Ready-to-show localized line, e.g. "Searching the web: profitking-trade.in". Absent from
   * older servers, which sent only {tool, status} - callers fall back to a local label map. */
  label?: string;
  /** Pairs a `start` with its matching `end` when a step runs several tool calls in parallel.
   * Absent from older servers (one tool call at a time, so `tool` alone identified it). */
  call_id?: string;
  proof?: Proof;
  /** Set on `end` only: whether the call succeeded. */
  ok?: boolean;
}

export interface AnswerEvent {
  text: string;
  cites: string[];
  actions: string[];
  chips: string[];
  fallback_used: boolean;
  /** Set when the model declined to answer (off-topic, or asking for stock/trade advice). The
   * refusal text itself is still a normal, renderable `answer` - this just flags it for a hint. */
  refused?: 'off_topic' | 'advice' | null;
}

export interface DoneEvent {
  case_id: string;
  timings: Record<string, number>;
}

export interface ErrorEvent {
  code: string;
  retryable: boolean;
  message_key: string;
}

export const RUN_EVENT_TYPES = [
  'stage',
  'image_reading',
  'entities',
  'plan',
  'check_result',
  'verdict',
  'explanation',
  'ask_user',
  'agent_step',
  'tool_status',
  'answer',
  'done',
  'error',
] as const;
export type RunEventType = (typeof RUN_EVENT_TYPES)[number];

export interface RunState {
  appliedIds: Set<number>;
  stage: Stage | null;
  imageReading: ImageReadingEvent | null;
  plan: PlanEvent | null;
  results: Record<string, CheckResultEvent>;
  verdict: VerdictEvent | null;
  explanation: ExplanationEvent | null;
  askUser: AskUserEvent | null;
  agentSteps: AgentStepEvent[];
  /** Latest `tool_status` per call, keyed by `label` (falls back to `tool` for older servers
   * that send no label) - lets `agentStepRows` join a step's actions to their live status. */
  toolCalls: Record<string, ToolStatusEvent>;
  toolStatus: ToolStatusEvent | null;
  answer: AnswerEvent | null;
  done: DoneEvent | null;
  error: ErrorEvent | null;
}

export function initialRunState(): RunState {
  return {
    appliedIds: new Set(),
    stage: null,
    imageReading: null,
    plan: null,
    results: {},
    verdict: null,
    explanation: null,
    askUser: null,
    agentSteps: [],
    toolCalls: {},
    toolStatus: null,
    answer: null,
    done: null,
    error: null,
  };
}

/** Applies one SSE event. Returns the SAME state object (not a copy) when `id` was already applied. */
export function applyRunEvent(state: RunState, id: number, type: string, data: unknown): RunState {
  if (state.appliedIds.has(id)) return state;
  const appliedIds = new Set(state.appliedIds);
  appliedIds.add(id);
  const next: RunState = { ...state, appliedIds };

  switch (type as RunEventType) {
    case 'stage':
      next.stage = (data as StageEvent).stage;
      return next;
    case 'image_reading':
      next.imageReading = data as ImageReadingEvent;
      return next;
    case 'entities':
      return next; // tracked for idempotency only; the checklist is built from `plan` + `check_result`
    case 'plan': {
      const plan = data as PlanEvent;
      if (!next.plan || plan.revision >= next.plan.revision) next.plan = plan;
      return next;
    }
    case 'check_result': {
      const result = data as CheckResultEvent;
      next.results = { ...next.results, [result.step_id]: result };
      return next;
    }
    case 'verdict': {
      const verdict = data as VerdictEvent;
      if (!next.verdict || verdict.revision >= next.verdict.revision) next.verdict = verdict;
      return next;
    }
    case 'explanation':
      next.explanation = data as ExplanationEvent;
      return next;
    case 'ask_user':
      next.askUser = data as AskUserEvent;
      return next;
    case 'agent_step':
      next.agentSteps = [...next.agentSteps, data as AgentStepEvent];
      return next;
    case 'tool_status': {
      const event = data as ToolStatusEvent;
      next.toolStatus = event;
      next.toolCalls = { ...next.toolCalls, [event.label ?? event.tool]: event };
      return next;
    }
    case 'answer':
      next.answer = data as AnswerEvent;
      return next;
    case 'done':
      next.done = data as DoneEvent;
      return next;
    case 'error':
      next.error = data as ErrorEvent;
      return next;
    default:
      return next;
  }
}

export type FamilyRowStatus = 'checking' | 'done' | 'unknown' | 'skipped';

/**
 * One checklist row's status (LLD §22.1): "checking..." while any step is pending/running,
 * "?" (unknown) when any finished step came back unknown or error, "-" when every step in the
 * family was skipped, else done. A step's outcome comes from its `check_result` once it has one;
 * until then we fall back to the plan step's own lifecycle status.
 */
export function familyRowStatus(family: string, state: RunState): FamilyRowStatus {
  const steps = (state.plan?.steps ?? []).filter((s) => s.family === family);
  if (steps.length === 0) return 'checking';
  const outcomes = steps.map((step) => {
    const result = state.results[step.id];
    return result ? result.status : step.status;
  });
  if (outcomes.some((o) => o === 'pending' || o === 'running')) return 'checking';
  if (outcomes.some((o) => o === 'unknown' || o === 'error')) return 'unknown';
  if (outcomes.every((o) => o === 'skipped')) return 'skipped';
  return 'done';
}

/** Families in the order their first step appears in the plan - stable row order as it grows. */
export function familiesInPlan(state: RunState): string[] {
  const seen = new Set<string>();
  const order: string[] = [];
  for (const step of state.plan?.steps ?? []) {
    if (!seen.has(step.family)) {
      seen.add(step.family);
      order.push(step.family);
    }
  }
  return order;
}

export interface AgentActionRow {
  tool: string;
  label: string;
  status: FamilyRowStatus; // 'skipped' never occurs here, but reusing the type avoids a second enum
}
export interface AgentStepRow {
  step: number;
  thought: string;
  actions: AgentActionRow[];
}

/**
 * One row per `agent_step`, in arrival order, with each action's live status joined from
 * `toolCalls` by its `label` - the one field both an `agent_step` action and its `tool_status`
 * call share (there is no call_id on the action itself to join by). Before that call's `start`
 * arrives an action already shows "checking" (the model has decided to run it); `ok: false` on
 * its `end` shows "unknown" (could not check), same as a rule-check row.
 */
export function agentStepRows(state: RunState): AgentStepRow[] {
  return state.agentSteps.map((step) => ({
    step: step.step,
    thought: step.thought,
    actions: step.actions.map((action) => {
      const call = state.toolCalls[action.label] ?? state.toolCalls[action.tool];
      const status: FamilyRowStatus = !call || call.status === 'start' ? 'checking' : call.ok === false ? 'unknown' : 'done';
      return { tool: action.tool, label: action.label, status };
    }),
  }));
}

/** Proofs of every finished step in a family, in plan order. */
export function familyProofs(family: string, state: RunState): Proof[] {
  return (state.plan?.steps ?? [])
    .filter((s) => s.family === family)
    .map((s) => state.results[s.id]?.proof)
    .filter((p): p is Proof => !!p);
}
