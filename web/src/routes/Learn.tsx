// /learn (CONTRACTS §7.2, LLD §21.2): the lesson list. Title in the current language with an
// English fallback; a check mark once IndexedDB progress says it's done. A "quick check" card
// (spaced re-test, task technique #4) sits above the list when an earlier quiz tactic was missed.
import { useEffect, useState } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { lessons, pick } from '../lib/lessons';
import { getProgress } from '../lib/idb';
import { getQuickCheck, recordMiss, clearMiss } from '../lib/retest';
import { Icon, type IconName } from '../components/Icon';
import { LearnArt } from '../components/Illustrations';

// Lesson topic -> icon (the lesson JSON ships an emoji; a consistent line-icon set reads as designed).
const LESSON_ICON: Record<string, IconName> = {
  compounding: 'trendingUp',
  'deepfake-ads': 'video',
  'digital-arrest': 'siren',
  'fake-apps': 'phoneApp',
  'ipo-allotment': 'document',
  'job-scam': 'job',
  'kyc-otp-remote-access': 'key',
  leverage: 'gauge',
  'pig-butchering': 'heartCrack',
  'sebi-registration': 'badge',
  'tips-and-pumps': 'megaphone',
  'withdrawal-fee-app': 'wallet',
};

export function Learn() {
  const done = useSignal<Record<string, boolean>>({});
  // One pick per page load - localStorage doesn't change under us, and "minimal" means no polling.
  const [quick] = useState(() => getQuickCheck());
  const [answered, setAnswered] = useState<string | null>(null);
  const lang = prefs.value.lang;

  useEffect(() => {
    void getProgress().then((p) => {
      const next: Record<string, boolean> = {};
      for (const [id, entry] of Object.entries(p.lessons)) next[id] = entry.done;
      done.value = next;
    });
  }, []);

  const doneCount = lessons.filter((l) => done.value[l.id]).length;

  return (
    <main class="screen screen-wide learn-screen">
      <header class="page-head">
        <LearnArt class="page-art" />
        <h1>{t('ui.learn')}</h1>
        <p class="lead">{t('ui.learn_sub')}</p>
        {lessons.length > 0 && (
          <div class="progress-row">
            <div class="progress" role="progressbar" aria-label={t('ui.lessons_done', { done: doneCount, total: lessons.length })} aria-valuemin={0} aria-valuemax={lessons.length} aria-valuenow={doneCount}>
              <span style={{ width: `${(doneCount / lessons.length) * 100}%` }} />
            </div>
            <span class="progress-label">{t('ui.lessons_done', { done: doneCount, total: lessons.length })}</span>
          </div>
        )}
      </header>

      {quick && (
        <section class="quick-check card" data-testid="quick-check">
          <p class="eyebrow">
            <Icon name="tactic" size={14} /> {t('ui.quick_check')}
          </p>
          <p class="quick-question">{pick(quick.question, lang)}</p>
          <div class="quiz-options">
            {quick.options.map((opt) => (
              <button
                key={opt.id}
                type="button"
                class={`btn quiz-option ${answered === opt.id ? (opt.correct ? 'correct' : 'incorrect') : ''}`}
                disabled={!!answered}
                onClick={() => {
                  setAnswered(opt.id);
                  if (quick.tactic) (opt.correct ? clearMiss : recordMiss)(quick.tactic);
                }}
              >
                {pick(opt.text, lang)}
              </button>
            ))}
          </div>
          {answered && quick.explain && <p class="quiz-explain">{pick(quick.explain, lang)}</p>}
        </section>
      )}

      {lessons.length === 0 && <p class="empty-state">{t('ui.no_lessons_yet')}</p>}
      <ul class="lesson-list card-grid">
        {lessons.map((lesson) => (
          <li key={lesson.id}>
            <a class={`lesson-row ${done.value[lesson.id] ? 'is-done' : ''}`} href={`/learn/${lesson.id}`}>
              <span class="lesson-icon-badge" aria-hidden="true">
                <Icon name={LESSON_ICON[lesson.id] ?? 'learn'} size={22} />
              </span>
              <span class="lesson-text">
                <span class="lesson-title">{pick(lesson.title, prefs.value.lang)}</span>
                {lesson.minutes != null && <span class="lesson-minutes">{t('ui.minutes', { n: lesson.minutes })}</span>}
              </span>
              {done.value[lesson.id] ? (
                <span class="lesson-done" aria-hidden="true">
                  ✓
                </span>
              ) : (
                <Icon name="chevronRight" size={18} className="lesson-chevron" />
              )}
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
