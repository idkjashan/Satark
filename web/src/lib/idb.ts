// Everything in IndexedDB (LLD §21.3), via idb-keyval's default store. One flat keyspace is enough
// for four unrelated small records - a custom store per concern would just be more files.
import { get, set, del, clear } from 'idb-keyval';

export interface HistoryEntry {
  date: string; // ISO timestamp
  level: string; // verdict level
  scam_type?: string;
  lesson?: string; // lesson id the verdict pointed at (drives "For you" and suggestions)
  lang: string;
}

const HISTORY_KEY = 'history';
const HISTORY_LIMIT = 20;

/** Last 20 checks, level + date only (CONTRACTS: the message itself is never stored). */
export async function addHistory(entry: HistoryEntry): Promise<void> {
  const list = (await get<HistoryEntry[]>(HISTORY_KEY)) ?? [];
  list.unshift(entry);
  await set(HISTORY_KEY, list.slice(0, HISTORY_LIMIT));
}

export async function getHistory(): Promise<HistoryEntry[]> {
  return (await get<HistoryEntry[]>(HISTORY_KEY)) ?? [];
}

/** History's own "Clear all" (LLD §21.2) - only the checks list, not progress/family/prefs. */
export async function clearHistory(): Promise<void> {
  await del(HISTORY_KEY);
}

export interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
  chips?: string[];
}
export interface ChatThread {
  id: string;
  title: string; // the first question
  date: string; // ISO timestamp of the last message
  messages: ChatMsg[];
}

const CHATS_KEY = 'chats';
const CHATS_LIMIT = 30;

export async function getThreads(): Promise<ChatThread[]> {
  return (await get<ChatThread[]>(CHATS_KEY)) ?? [];
}

/** Upsert one thread, newest first, capped at 30. Stays on this device (cleared by "Clear my data"). */
export async function saveThread(thread: ChatThread): Promise<void> {
  const rest = (await getThreads()).filter((x) => x.id !== thread.id);
  await set(CHATS_KEY, [thread, ...rest].slice(0, CHATS_LIMIT));
}

export async function deleteThread(id: string): Promise<void> {
  await set(CHATS_KEY, (await getThreads()).filter((x) => x.id !== id));
}

export async function clearThreads(): Promise<void> {
  await del(CHATS_KEY);
}

export interface Progress {
  lessons: Record<string, { done: boolean; quiz_before?: boolean; quiz_after?: boolean }>;
  sims: Record<string, string>; // sim id -> outcome id
}

const PROGRESS_KEY = 'progress';

export async function getProgress(): Promise<Progress> {
  const p = await get<Progress>(PROGRESS_KEY);
  return p ?? { lessons: {}, sims: {} };
}

export async function recordLessonQuiz(id: string, when: 'before' | 'after', correct: boolean): Promise<void> {
  const progress = await getProgress();
  const prior = progress.lessons[id] ?? { done: false };
  progress.lessons[id] = { ...prior, [when === 'before' ? 'quiz_before' : 'quiz_after']: correct };
  await set(PROGRESS_KEY, progress);
}

// quizAfter is folded into the same write: two concurrent read-modify-writes lost one update.
export async function markLessonDone(id: string, quizAfter?: boolean): Promise<void> {
  const progress = await getProgress();
  const prior = progress.lessons[id] ?? {};
  progress.lessons[id] = { ...prior, done: true, ...(quizAfter === undefined ? {} : { quiz_after: quizAfter }) };
  await set(PROGRESS_KEY, progress);
}

export async function recordSimOutcome(id: string, outcome: string): Promise<void> {
  const progress = await getProgress();
  progress.sims[id] = outcome;
  await set(PROGRESS_KEY, progress);
}

export interface Family {
  name?: string;
  phone?: string;
}

const FAMILY_KEY = 'family';

export async function getFamily(): Promise<Family> {
  return (await get<Family>(FAMILY_KEY)) ?? {};
}

export async function setFamily(f: Family): Promise<void> {
  await set(FAMILY_KEY, f);
}

export interface SharePayload {
  title?: string;
  text?: string;
  url?: string;
  files?: Blob[];
}

/** Reads and deletes the service worker's share-target payload (one-shot, LLD §22.2). */
export async function takeSharePayload(id: string): Promise<SharePayload | undefined> {
  const key = `share:${id}`;
  const payload = await get<SharePayload>(key);
  if (payload) await del(key);
  return payload;
}

/** "Clear my data" (Settings). Prefs (localStorage) are reset separately via resetPrefs(). */
export async function clearAllData(): Promise<void> {
  await clear();
}
