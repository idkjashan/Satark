// /quiz?topic=<lesson id or free text>&scam_type=<T1..T17>: a model-written 3-question quiz
// (POST /v1/practice), rendered by QuizFlow. Misses feed the quick-check pool like any other quiz.
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { postPractice, type PracticeResult } from '../lib/api';
import { QuizFlow } from '../components/QuizFlow';
import { Icon } from '../components/Icon';

export function Quiz() {
  const { query } = useLocation();
  const result = useSignal<PracticeResult | null>(null);
  const failed = useSignal(false);

  useEffect(() => {
    postPractice({ topic: query.topic || undefined, scam_type: query.scam_type || undefined, lang: prefs.value.lang })
      .then((r) => (result.value = r))
      .catch(() => (failed.value = true));
  }, [query.topic, query.scam_type]);

  return (
    <main class="screen" data-testid="practice-quiz">
      {failed.value ? (
        <>
          <p role="alert">{t('ui.quiz_failed')}</p>
          <a class="btn btn-primary" href="/learn">
            {t('ui.learn')}
          </a>
        </>
      ) : result.value && result.value.questions.length > 0 ? (
        <QuizFlow questions={result.value.questions} doneHref="/learn" />
      ) : (
        <p class="stage-label" role="status">
          <Icon name="loader" size={18} spin /> {t('ui.quiz_loading')}
        </p>
      )}
    </main>
  );
}
