// Shared quiz UI (LessonPlayer, SimPlayer): one question per screen, big buttons, immediate
// correct/incorrect feedback plus a one-line explain, then Next or Done. A question tagged with a
// `tactic` id feeds the spaced re-test pool (lib/retest.ts) on every answer, right or wrong.
// The caller wraps this in its own <main data-testid="lesson-quiz"|"sim-quiz"> (LLD §23.4).
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { pick, type QuizQuestion } from '../lib/lessons';
import { recordMiss, clearMiss } from '../lib/retest';
import { Icon } from './Icon';

interface QuizFlowProps {
  questions: QuizQuestion[];
  doneHref: string;
  /** Called once, right when the last question is answered - `allCorrect` covers every question
   * in this run, not just the last one. */
  onFinish?: (allCorrect: boolean) => void;
}

export function QuizFlow({ questions, doneHref, onFinish }: QuizFlowProps) {
  const lang = prefs.value.lang;
  const [index, setIndex] = useState(0);
  const [answered, setAnswered] = useState<string | null>(null);
  const [missedAny, setMissedAny] = useState(false);
  const q = questions[index];
  if (!q) return null;
  const isLast = index === questions.length - 1;

  return (
    <>
      <header class="page-head">
        <p class="eyebrow">{t('ui.question_of', { n: index + 1, total: questions.length })}</p>
        <h1>{pick(q.question, lang)}</h1>
      </header>
      <div class="quiz-options">
        {q.options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            class={`btn quiz-option ${answered === opt.id ? (opt.correct ? 'correct' : 'incorrect') : ''}`}
            data-testid={`quiz-option-${opt.id}`}
            disabled={!!answered}
            onClick={() => {
              setAnswered(opt.id);
              if (q.tactic) (opt.correct ? clearMiss : recordMiss)(q.tactic);
              if (!opt.correct) setMissedAny(true);
            }}
          >
            {pick(opt.text, lang)}
          </button>
        ))}
      </div>
      {answered && (
        <>
          <div class={`quiz-feedback ${q.options.find((o) => o.id === answered)?.correct ? 'is-correct' : 'is-wrong'}`} role="status">
            <p class="quiz-verdict">
              <Icon name={q.options.find((o) => o.id === answered)?.correct ? 'checkCircle' : 'alertCircle'} size={18} />
              {q.options.find((o) => o.id === answered)?.correct ? t('ui.quiz_correct') : t('ui.quiz_wrong')}
            </p>
            {q.explain && <p class="quiz-explain">{pick(q.explain, lang)}</p>}
          </div>
          <div class="sticky-action">
            {isLast ? (
              <a class="btn btn-primary btn-huge" href={doneHref} onClick={() => onFinish?.(!missedAny)}>
                {t('ui.done')}
              </a>
            ) : (
              <button
                type="button"
                class="btn btn-primary btn-huge"
                onClick={() => {
                  setIndex((i) => i + 1);
                  setAnswered(null);
                }}
              >
                {t('ui.next')}
              </button>
            )}
          </div>
        </>
      )}
    </>
  );
}
