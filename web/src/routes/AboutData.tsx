// /about-data (CONTRACTS §6 `GET /v1/meta`, LLD §21.2): what we check, how fresh it is, and an
// honest "this can be wrong" line - never "safe".
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { formatAsOn } from '../lib/format';
import { getMeta, type MetaResponse } from '../lib/api';
import { Icon } from '../components/Icon';

export function AboutData() {
  const meta = useSignal<MetaResponse | null>(null);
  const failed = useSignal(false);

  useEffect(() => {
    getMeta()
      .then((m) => (meta.value = m))
      .catch(() => (failed.value = true));
  }, []);

  return (
    <main class="screen about-data-screen">
      <h1>{t('ui.about_data')}</h1>
      <p class="prototype-disclaimer">
        <Icon name="helpCircle" size={20} /> {t('ui.prototype_disclaimer')}
      </p>

      {failed.value && <p>{t('ui.meta_unavailable')}</p>}

      {meta.value && (
        <>
          <section>
            <h2>{t('ui.sources')}</h2>
            <ul>
              {meta.value.sources.map((s) => (
                <li key={s.id}>
                  {s.name} · {formatAsOn(s.as_on, prefs.value.lang)} · {s.status}
                </li>
              ))}
            </ul>
          </section>

          {meta.value.disabled_checkers.length > 0 && (
            <section>
              <h2>{t('ui.disabled_checks')}</h2>
              <ul>
                {meta.value.disabled_checkers.map((d) => (
                  <li key={d.id}>
                    {d.id}: {d.reason}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p class="version-line">
            {t('ui.version')}: {meta.value.version}
          </p>
        </>
      )}
    </main>
  );
}
