// Personalisation from on-device data only: past checks (idb history), missed quiz tactics
// (retest.ts) and the last lesson opened. Feeds the suggestion chips and Learn's "For you".
import { getHistory } from './idb';
import { readMissed } from './retest';
import { lessons, getLesson, pick, type Lesson } from './lessons';
import { getSim } from './sims';
import { t } from './i18n';
import { prefs } from './signals';

const LAST_LESSON = 'last_lesson';

export function setLastLesson(id: string): void {
  try {
    localStorage.setItem(LAST_LESSON, id);
  } catch {
    // private mode: just not remembered
  }
}

function lastLesson(): string | null {
  try {
    return localStorage.getItem(LAST_LESSON);
  } catch {
    return null;
  }
}

function lessonsForMissed(): Lesson[] {
  const missed = readMissed();
  return lessons.filter((l) => missed.includes(l.tacticKey ?? '') || (Array.isArray(l.quiz) ? l.quiz : l.quiz ? [l.quiz] : []).some((q) => q.tactic && missed.includes(q.tactic)));
}

/** Up to 3 lessons then sims, in priority order: lessons from past verdicts (newest first), then
 * lessons whose tactics were missed, then the sims those lessons link to. */
export async function recommendations(): Promise<{ lessons: Lesson[]; sims: { id: string; title: Record<string, string> }[] }> {
  const ids = (await getHistory()).map((h) => h.lesson).filter((x): x is string => !!x);
  const picked = [...new Set([...ids, ...lessonsForMissed().map((l) => l.id)])].map((id) => getLesson(id)).filter((l): l is Lesson => !!l);
  const top = picked.slice(0, 3);
  const simIds = [...new Set(top.map((l) => l.sim).filter((x): x is string => !!x))].slice(0, 2);
  const sims = simIds.map((id) => getSim(id)).filter((s) => !!s).map((s) => ({ id: s!.id, title: s!.title ?? {} }));
  return { lessons: top, sims };
}

/** Three question strings for Chat's empty state and Home: from the user's own history, else `fallback`. */
export async function suggestions(fallback: string[]): Promise<string[]> {
  const lang = prefs.value.lang;
  const out: string[] = [];
  const [last] = await getHistory();
  if (last?.scam_type) out.push(t('ui.suggest_scam', { type: t(`scam_type.${last.scam_type}`) }));
  const lessonIds = [last?.lesson, ...lessonsForMissed().map((l) => l.id), lastLesson()];
  for (const id of lessonIds) {
    const l = id ? getLesson(id) : undefined;
    if (l) out.push(t('ui.suggest_lesson', { title: pick(l.title, lang) }));
  }
  return [...new Set([...out, ...fallback])].slice(0, 3);
}
