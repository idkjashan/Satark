// HTTP + SSE client for the Satark API (CONTRACTS §6). Same origin, no cookies, no CORS.
import { signal } from '@preact/signals';
import { RUN_EVENT_TYPES, type RunEventType } from './runReducer';

export type { RunEventType };

export interface RunHandle {
  run_id: string;
  case_id: string;
  events_url: string;
  expires_at: string;
}

/** Every non-2xx response body is {error: {code, message_key, retryable}} (CONTRACTS §6). */
export class ApiError extends Error {
  status: number;
  code: string;
  messageKey: string;
  retryable: boolean;
  constructor(status: number, code: string, messageKey: string, retryable: boolean) {
    super(code);
    this.status = status;
    this.code = code;
    this.messageKey = messageKey;
    this.retryable = retryable;
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  try {
    const json = (await res.json()) as { error?: { code?: string; message_key?: string; retryable?: boolean } };
    const err = json.error ?? {};
    return new ApiError(res.status, err.code ?? 'internal', err.message_key ?? '', !!err.retryable);
  } catch {
    return new ApiError(res.status, 'internal', '', false);
  }
}

/** 10s timeout, one retry on a network error (not on an HTTP error status). */
async function fetchWithRetry(path: string, init: RequestInit, timeoutMs = 10000): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(path, { ...init, signal: controller.signal });
    } catch (err) {
      lastError = err;
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithRetry(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetchWithRetry(path, { method: 'POST', body: form });
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

export interface CheckInput {
  text?: string;
  image?: Blob;
  qr?: string;
  lang: string;
  simple: boolean;
}

/** The most recent /v1/checks input, kept only in memory so Run.tsx can retry once on
 *  run_not_found (LLD §22.1). Never persisted - this is exactly the message content that
 *  CONTRACTS says must never leave the phone except over the wire for the check itself. */
export const lastCheckInput = signal<CheckInput | null>(null);

/** The most recent case id seen by Run.tsx or Chat.tsx, in memory only. /help-paid uses it to
 *  ask for a real POST /v1/report-draft instead of falling back to a local template. */
export const lastCaseId = signal<string | null>(null);

export async function postCheck(input: CheckInput): Promise<RunHandle> {
  const form = new FormData();
  if (input.text) form.set('text', input.text);
  if (input.image) form.set('image', input.image, 'screenshot.jpg');
  if (input.qr) form.set('qr', input.qr);
  form.set('lang', input.lang);
  form.set('simple', String(input.simple));
  form.set('client', 'pwa');
  return postForm<RunHandle>('/v1/checks', form);
}

export interface ChatInput {
  case_id?: string;
  message?: string;
  choice?: { question_id: string; option_id: string };
  lang: string;
  simple?: boolean;
}

export async function postChat(input: ChatInput): Promise<RunHandle> {
  return postJSON<RunHandle>('/v1/chat', input);
}

export interface ReportDraftInput {
  case_id: string;
  lang: string;
  answers: { when?: string; how_paid?: string; amount_band?: string };
}
export interface ReportDraft {
  text_en: string;
  text_lang: string;
  evidence: { label: string; value: string }[];
  portals: { id: string; name: string; url: string; phone?: string }[];
}

export async function postReportDraft(input: ReportDraftInput): Promise<ReportDraft> {
  return postJSON<ReportDraft>('/v1/report-draft', input);
}

export interface MetaResponse {
  sources: { id: string; name: string; as_on: string; status: string; rows?: number }[];
  languages: { code: string; name: string; native: string; speech: string }[];
  disabled_checkers: { id: string; reason: string }[];
  llm: Record<string, string>;
  scoring_version: string;
  version: string;
}

export interface FeedbackInput {
  case_id?: string;
  kind: 'helpful' | 'mistake';
  level?: string;
  reason_codes?: string[];
}

/** POST /v1/feedback (CONTRACTS §6): 204 no body, an anonymous counter server-side - postJSON
 * assumes a JSON body on success, which a 204 never has, so this calls fetchWithRetry directly. */
export async function postFeedback(input: FeedbackInput): Promise<void> {
  const res = await fetchWithRetry('/v1/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await errorFrom(res);
}

export async function getMeta(): Promise<MetaResponse> {
  const res = await fetchWithRetry('/v1/meta', { method: 'GET' });
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as MetaResponse;
}

// ---- SSE run events --------------------------------------------------------------------

export interface RunEventHandlers {
  onEvent: (type: RunEventType, id: number, data: unknown) => void;
  /** No event at all for 12s (LLD §22.1): show "Slow network..." with a manual Retry. */
  onSlow?: () => void;
  /** The stream could never be opened (e.g. 404 run_not_found): the browser gave up for good. */
  onConnectionFailed?: () => void;
}

export interface RunSubscription {
  close: () => void;
  /** Re-opens the connection; the reducer's idempotency makes a full replay from id 0 harmless. */
  retry: () => void;
}

const WATCHDOG_MS = 12_000;

/**
 * Subscribes to `GET /v1/runs/{id}/events` (or the chat equivalent). The browser's native
 * EventSource already resends `Last-Event-ID` and auto-reconnects on a dropped connection; we
 * only add the 12s "slow network" watchdog and detect the one case the browser won't retry:
 * a response that failed outright (readyState goes CLOSED, not CONNECTING).
 */
export function openRunEvents(eventsUrl: string, handlers: RunEventHandlers): RunSubscription {
  let es: EventSource | null = null;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let gotAny = false;

  function armWatchdog(): void {
    if (watchdog) clearTimeout(watchdog);
    watchdog = setTimeout(() => handlers.onSlow?.(), WATCHDOG_MS);
  }

  function connect(): void {
    gotAny = false;
    const source = new EventSource(eventsUrl);
    es = source;
    armWatchdog();
    for (const type of RUN_EVENT_TYPES) {
      source.addEventListener(type, (event) => {
        gotAny = true;
        armWatchdog();
        const raw = (event as MessageEvent).data as string;
        let data: unknown = {};
        try {
          data = JSON.parse(raw);
        } catch {
          // malformed payload: skip rather than crash the reducer
          return;
        }
        handlers.onEvent(type, Number((event as MessageEvent).lastEventId), data);
      });
    }
    source.onerror = () => {
      if (!gotAny && source.readyState === EventSource.CLOSED) {
        handlers.onConnectionFailed?.();
      }
    };
  }

  connect();

  return {
    close: () => {
      if (watchdog) clearTimeout(watchdog);
      es?.close();
    },
    retry: () => {
      es?.close();
      connect();
    },
  };
}
