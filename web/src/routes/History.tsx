// /history (product spec, Oct 2026): every past check this device remembers - level and date
// only, same privacy rule as Home's "Recent checks" preview (CONTRACTS: the message text itself
// is never stored). "Clear all" removes just this list (idb.clearHistory), not every preference.
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { t } from '../lib/i18n';
import { getHistory, clearHistory, type HistoryEntry } from '../lib/idb';

export function History() {
  const history = useSignal<HistoryEntry[] | null>(null);

  useEffect(() => {
    void getHistory().then((h) => (history.value = h));
  }, []);

  return (
    <main class="screen" data-testid="history-screen">
      <h1>{t('ui.history')}</h1>

      {history.value === null ? (
        <ul class="skeleton-list" aria-hidden="true">
          <li class="skeleton-row" />
          <li class="skeleton-row" />
          <li class="skeleton-row" />
        </ul>
      ) : history.value.length === 0 ? (
        <p class="empty-state">{t('ui.history_empty')}</p>
      ) : (
        <>
          <ul class="history-list">
            {history.value.map((entry, i) => (
              <li key={i} class="history-row">
                <span class={`level-dot level-${entry.level}`} aria-hidden="true" />
                <span class="history-level">{t(`level.${entry.level}.headline`)}</span>
                <span class="history-date">{new Date(entry.date).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            class="btn btn-danger"
            onClick={async () => {
              await clearHistory();
              history.value = [];
            }}
          >
            {t('ui.clear_all')}
          </button>
        </>
      )}
    </main>
  );
}
