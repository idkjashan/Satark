// /practice (CONTRACTS §7.3, LLD §21.2): the simulator list.
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { sims } from '../lib/sims';
import { pick } from '../lib/lessons';
import { Icon, type IconName } from '../components/Icon';

// sims.json carries no icon/description field (G's content, CONTRACTS §7.3 SimMeta = id/kind/title
// only) - `kind` picks a fitting icon (shared across same-kind sims is fine), and `id` picks the
// one-line "what is this" caption (each sim's own scenario, so S4-S6 don't inherit S1's text).
const KIND_ICON: Record<string, IconName> = { fsm: 'warningTriangle', returns: 'practice', leverage: 'alertCircle' };
const SIM_DESC: Record<string, string> = {
  S1: 'ui.sim_desc_S1',
  S2: 'ui.sim_desc_S2',
  S3: 'ui.sim_desc_S3',
  S4: 'ui.sim_desc_S4',
  S5: 'ui.sim_desc_S5',
  S6: 'ui.sim_desc_S6',
};

export function Practice() {
  return (
    <main class="screen screen-wide">
      <header class="page-head">
        <h1>{t('ui.practice')}</h1>
        <p class="lead">{t('ui.practice_sub')}</p>
      </header>
      {sims.length === 0 && <p class="empty-state">{t('ui.no_sims_yet')}</p>}
      <ul class="lesson-list card-grid">
        {sims.map((sim) => (
          <li key={sim.id}>
            <a class="lesson-row" href={`/sim/${sim.id}`}>
              <span class="lesson-icon-badge" aria-hidden="true">
                <Icon name={KIND_ICON[sim.kind] ?? 'practice'} size={22} />
              </span>
              <span class="lesson-text">
                <span class="lesson-title">{pick(sim.title, prefs.value.lang) || sim.id}</span>
                {SIM_DESC[sim.id] && <span class="lesson-desc">{t(SIM_DESC[sim.id])}</span>}
                <span class="pill pill-ok">{t('ui.zero_risk')}</span>
              </span>
              <Icon name="chevronRight" size={18} className="lesson-chevron" />
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
