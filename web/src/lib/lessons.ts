// Lesson content (CONTRACTS §7.2), loaded eagerly so /learn works offline once precached.
// Engineer G writes content/lessons/*.json in parallel - zero files is a valid, handled state.
export type LangText = Record<string, string>;

export interface LessonStep {
  text: LangText;
  visual?: string;
}
export interface LessonQuizOption {
  id: string;
  text: LangText;
  correct?: boolean;
}
/** One quiz question (CONTRACTS SS7.2/7.3 extension, task's "immediate retrieval" quizzes).
 * `tactic` is a plain machine key (e.g. "pay_to_withdraw"), not bilingual - it feeds the spaced
 * re-test pool in lib/retest.ts, not the UI. */
export interface QuizQuestion {
  question: LangText;
  options: LessonQuizOption[];
  explain?: LangText;
  tactic?: string;
}
export interface Lesson {
  id: string;
  icon?: string;
  minutes?: number;
  title: LangText;
  /** Prebunking (task technique #2): the one line every lesson opens with, naming the
   * manipulation tactic before the user meets it "in the wild". */
  tactic?: LangText;
  tacticKey?: string;
  /** One citation URL for the lesson's facts (helpline 1930, cybercrime.gov.in, SEBI check, ...). */
  source?: string;
  /** A linked simulator id (content/sims/<id>.json) to "try it" from the lesson's last screen. */
  sim?: string;
  steps: LessonStep[];
  analogy?: LangText;
  quiz?: QuizQuestion | QuizQuestion[];
}

/** A lesson/sim `quiz` is one question (older content) or a list of 2-3 - always work with a list. */
export function quizQuestions(quiz: QuizQuestion | QuizQuestion[] | undefined): QuizQuestion[] {
  if (!quiz) return [];
  return Array.isArray(quiz) ? quiz : [quiz];
}

const modules = import.meta.glob<Lesson>('@content/lessons/*.json', { eager: true, import: 'default' });
export const lessons: Lesson[] = Object.values(modules);

export function getLesson(id: string): Lesson | undefined {
  return lessons.find((l) => l.id === id);
}

/** Current language, English fallback, then "" - mirrors the i18n fallback rule for content JSON. */
export function pick(text: LangText | undefined, lang: string): string {
  return text?.[lang] ?? text?.en ?? '';
}
