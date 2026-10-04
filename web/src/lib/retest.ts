// Spaced re-test (SANGYAN Track C technique #4: the Cambridge "Bad News" game effect only held
// up with repeated testing). Missed quiz "tactics" persist in localStorage - small and synchronous,
// unlike the IndexedDB progress store in lib/idb.ts - so a later /learn visit can re-probe one of
// them with a single "quick check" question pulled from any lesson/sim quiz tagged with that tactic.
import { lessons, quizQuestions, type QuizQuestion } from './lessons';
import { sims } from './sims';

const KEY = 'missed_tactics';

export function readMissed(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return []; // storage unavailable (private mode) - re-test just does nothing this session
  }
}

function writeMissed(list: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // quota or private mode - the miss just isn't remembered for next time
  }
}

/** Called when a tagged quiz question is answered wrong. */
export function recordMiss(tactic: string): void {
  const list = readMissed();
  if (!list.includes(tactic)) writeMissed([...list, tactic]);
}

/** Called when a tagged quiz question is answered right - one less thing to re-test. */
export function clearMiss(tactic: string): void {
  const list = readMissed();
  if (list.includes(tactic)) writeMissed(list.filter((t) => t !== tactic));
}

/** Settings' "Clear my data". */
export function clearAllMissed(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

/** Every tagged quiz question across lessons + sims, pooled once per call - content is static,
 * so this is cheap enough to not bother caching. */
function taggedPool(): QuizQuestion[] {
  const pool: QuizQuestion[] = [];
  for (const l of lessons) pool.push(...quizQuestions(l.quiz).filter((q) => q.tactic));
  for (const s of sims) pool.push(...quizQuestions(s.quiz).filter((q) => q.tactic));
  return pool;
}

/** One question for the Learn screen's "quick check" card: the earliest still-missed tactic that
 * has a matching question in the content pool - or undefined if nothing is missed, or missed but
 * untagged in content (never happens in practice, but no crash either way). */
export function getQuickCheck(): QuizQuestion | undefined {
  const missed = readMissed();
  if (!missed.length) return undefined;
  const pool = taggedPool();
  for (const tactic of missed) {
    const match = pool.find((q) => q.tactic === tactic);
    if (match) return match;
  }
  return undefined;
}
