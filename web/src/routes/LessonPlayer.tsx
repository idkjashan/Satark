// /learn/:id (LLD §23.4): one step per screen with a big Next, a read-aloud button, a tactic
// banner on the opening screen (prebunking), an analogy card after the last step, then a 1-3
// question quiz. Attempts/correctness go to IndexedDB progress.
import { useState } from 'preact/hooks';
import { getLesson, pick, quizQuestions } from '../lib/lessons';
import { prefs } from '../lib/signals';
import { t } from '../lib/i18n';
import { markLessonDone } from '../lib/idb';
import { setLastLesson } from '../lib/personal';
import { Visual } from '../components/visuals';
import { SpeakerButton } from '../components/SpeakerButton';
import { QuizFlow } from '../components/QuizFlow';
import { Icon } from '../components/Icon';

interface LessonPlayerProps {
  id: string;
}

export function LessonPlayer({ id }: LessonPlayerProps) {
  const lesson = getLesson(id);
  if (lesson) setLastLesson(id);
  const [step, setStep] = useState(0);
  const [showQuiz, setShowQuiz] = useState(false);
  const lang = prefs.value.lang;

  if (!lesson) {
    return (
      <main class="screen">
        <p>{t('ui.lesson_not_found')}</p>
        <a class="btn" href="/learn">
          {t('ui.learn')}
        </a>
      </main>
    );
  }

  if (showQuiz && lesson.quiz) {
    return (
      <main class="screen" data-testid="lesson-quiz">
        <QuizFlow
          questions={quizQuestions(lesson.quiz)}
          doneHref="/learn"
          onFinish={(allCorrect) => {
            void markLessonDone(lesson.id, allCorrect);
          }}
        />
      </main>
    );
  }

  const current = lesson.steps[step];
  const isLast = step === lesson.steps.length - 1;
  const text = pick(current.text, lang);

  return (
    <main class="screen lesson-player">
      <header class="page-head">
        <p class="eyebrow">{t('ui.step_of', { n: step + 1, total: lesson.steps.length })}</p>
        <h1>{pick(lesson.title, lang)}</h1>
        <div class="progress" role="progressbar" aria-label={t('ui.step_of', { n: step + 1, total: lesson.steps.length })} aria-valuemin={0} aria-valuemax={lesson.steps.length} aria-valuenow={step + 1}>
          <span style={{ width: `${((step + 1) / lesson.steps.length) * 100}%` }} />
        </div>
      </header>
      {step === 0 && lesson.tactic && (
        <div class="tactic-banner" data-testid="lesson-tactic">
          <Icon name="tactic" size={20} />
          <p>{pick(lesson.tactic, lang)}</p>
        </div>
      )}
      <div class="lesson-card card">
        <Visual name={current.visual} />
        <p class="lesson-step-text">{text}</p>
        <SpeakerButton text={text} lang={lang} />
      </div>

      {isLast && lesson.analogy && (
        <div class="analogy-card">
          <p>{pick(lesson.analogy, lang)}</p>
        </div>
      )}

      {isLast && lesson.sim && (
        <a class="btn" href={`/sim/${lesson.sim}`}>
          <Icon name="practice" size={18} /> {t('ui.try_simulator')}
        </a>
      )}

      {isLast && lesson.source && (
        <p class="lesson-source">
          <a href={lesson.source} target="_blank" rel="noopener noreferrer">
            {t('ui.lesson_source')}
          </a>
        </p>
      )}

      <div class="sticky-action">
        {isLast && !lesson.quiz ? (
          <a class="btn btn-primary btn-huge" data-testid="lesson-next" href="/learn" onClick={() => void markLessonDone(lesson.id)}>
            {t('ui.done')}
          </a>
        ) : (
          <button
            type="button"
            class="btn btn-primary btn-huge"
            data-testid="lesson-next"
            onClick={() => (isLast ? setShowQuiz(true) : setStep((s) => s + 1))}
          >
            {isLast ? t('ui.quiz') : t('ui.next')} <Icon name="arrowRight" size={18} />
          </button>
        )}
      </div>
    </main>
  );
}
