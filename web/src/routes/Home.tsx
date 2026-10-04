// / (Home) - two equal primary actions (product update, Oct 2026): checking a message is one
// half of what Satark does, asking or learning is the other - Track C is first-class, not a
// footnote. Pure navigation uses plain <a href>: preact-iso's LocationProvider intercepts
// same-origin clicks itself, so no onClick/route() plumbing is needed for any of it.
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { t } from '../lib/i18n';
import { getHistory, type HistoryEntry } from '../lib/idb';
import { Icon } from '../components/Icon';
import { HeroArt } from '../components/Illustrations';
import { speak } from '../lib/voice';

/** Small speaker under a tile: reads what the tile does aloud, so it can be used without reading. */
function HearButton({ text }: { text: string }) {
  return (
    <button type="button" class="hear-btn" aria-label={`${t('ui.listen')}: ${text}`} onClick={() => void speak(text)}>
      <Icon name="speaker" size={22} />
      <span>{t('ui.listen')}</span>
    </button>
  );
}

// content.<lang>.json already has these exact examples (engineer G) - reusing them means one
// fewer set of strings to keep translated, and they match the chips a real answer would use.
const ASK_EXAMPLES = ['chip.what_is_sip', 'chip.is_rate_possible', 'chip.spot_fake_adviser'];

export function Home() {
  const history = useSignal<HistoryEntry[]>([]);

  useEffect(() => {
    void getHistory().then((h) => (history.value = h));
  }, []);

  return (
    <main class="screen screen-wide home-screen">
      <section class="home-hero">
        <div class="hero-copy">
          <p class="eyebrow">Satark · सतर्क</p>
          <h1 class="home-title">{t('ui.home_title')}</h1>
          <p class="lead">{t('ui.home_sub')}</p>
          <a class="btn btn-hero hero-cta" href="/check">
            <Icon name="check" size={22} />
            {t('ui.check_a_message')}
          </a>
        </div>
        <HeroArt class="hero-art" />
      </section>

      <section class="big-tiles" aria-label={t('ui.home_title')}>
        <div class="big-tile-wrap">
          <a class="big-tile tile-check" data-testid="home-check" href="/check">
            <span class="big-tile-icon">
              <Icon name="check" size={40} />
            </span>
            {t('ui.check_a_message')}
          </a>
          <HearButton text={t('ui.hear_check')} />
        </div>
        <div class="big-tile-wrap">
          <a class="big-tile tile-ask" href="/chat/new">
            <span class="big-tile-icon">
              <Icon name="mic" size={40} />
            </span>
            {t('ui.ask_or_learn')}
          </a>
          <HearButton text={t('ui.hear_ask')} />
        </div>
        <div class="big-tile-wrap">
          <a class="big-tile tile-learn" data-testid="home-learn" href="/learn">
            <span class="big-tile-icon">
              <Icon name="learn" size={40} />
            </span>
            {t('ui.learn')}
          </a>
          <HearButton text={t('ui.hear_learn')} />
        </div>
      </section>

      <div class="chips ask-chips">
        {ASK_EXAMPLES.map((key) => (
          <a key={key} class="chip" href={`/chat/new?q=${encodeURIComponent(t(key))}`}>
            {t(key)}
          </a>
        ))}
      </div>

      <div class="home-tiles">
        <a class="tile" data-testid="home-practice" href="/practice">
          <Icon name="practice" size={22} />
          {t('ui.practice')}
        </a>
        <a class="tile tile-help" data-testid="home-help" href="/help-paid">
          <Icon name="shieldAlert" size={22} />
          {t('ui.already_paid')}
        </a>
      </div>

      <section class="how-it-works">
        <h2>{t('ui.how_title')}</h2>
        <ol class="how-steps">
          <li>
            <span class="how-icon">
              <Icon name="paste" size={26} />
            </span>
            <span class="how-num">1</span>
            <p>{t('ui.how_1')}</p>
          </li>
          <li>
            <span class="how-icon">
              <Icon name="landmark" size={26} />
            </span>
            <span class="how-num">2</span>
            <p>{t('ui.how_2')}</p>
          </li>
          <li>
            <span class="how-icon">
              <Icon name="shieldAlert" size={26} />
            </span>
            <span class="how-num">3</span>
            <p>{t('ui.how_3')}</p>
          </li>
        </ol>
      </section>

      {history.value.length > 0 && (
        <section class="home-history card">
          <div class="home-history-head">
            <h2>{t('ui.recent_checks')}</h2>
            <a class="btn-link" href="/history">
              {t('ui.see_all')}
            </a>
          </div>
          <ul>
            {history.value.slice(0, 5).map((entry, i) => (
              <li key={i}>
                <span class={`level-dot level-${entry.level}`} aria-hidden="true" />
                <span class="history-text">{t(`level.${entry.level}.headline`)}</span>
                <span class="history-date">{new Date(entry.date).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer class="home-footer">
        <p>
          <Icon name="lock" size={14} /> {t('ui.footer_promise')}
        </p>
        <nav aria-label={t('ui.nav_more')}>
          <a href="/history">{t('ui.history')}</a>
          <a href="/about-data">{t('ui.about_data')}</a>
          <a href="/settings">{t('ui.settings')}</a>
        </nav>
      </footer>
    </main>
  );
}
