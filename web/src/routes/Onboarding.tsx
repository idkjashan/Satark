// /onboarding (LLD §21.2): pick a language (each card speaks its own name), the Simple-mode
// toggle, a one-screen privacy notice, and an install prompt when the browser offers one.
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs, setPrefs } from '../lib/signals';
import { speak } from '../lib/voice';
import { enabledLanguages, ensureLanguagesLoaded } from '../lib/languages';
import { HeroArt } from '../components/Illustrations';
import { Shield } from '../components/Shield';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
}

export function Onboarding() {
  const { route } = useLocation();
  const installEvent = useSignal<InstallPromptEvent | null>(null);

  useEffect(() => {
    ensureLanguagesLoaded();

    function onBeforeInstall(e: Event) {
      e.preventDefault();
      installEvent.value = e as InstallPromptEvent;
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    return () => window.removeEventListener('beforeinstallprompt', onBeforeInstall);
  }, []);

  function pickLanguage(code: string, native: string) {
    setPrefs({ lang: code });
    void speak(native, code);
  }

  return (
    <main class="screen onboarding-screen">
      <div class="onboarding-brand">
        <Shield size={48} />
        <span class="brand-name">Satark</span>
      </div>
      <h1>{t('ui.choose_language')}</h1>
      <div class="onboard-hero">
        <HeroArt class="onboard-art" size={240} />
      </div>
      <div class="lang-cards">
        {enabledLanguages.value.map((lang) => (
          <button
            key={lang.code}
            type="button"
            class={`lang-card ${prefs.value.lang === lang.code ? 'selected' : ''}`}
            data-testid={`lang-${lang.code}`}
            aria-pressed={prefs.value.lang === lang.code}
            onClick={() => pickLanguage(lang.code, lang.native)}
          >
            {lang.native}
          </button>
        ))}
      </div>

      <label class="simple-toggle-row">
        <input
          type="checkbox"
          data-testid="simple-toggle"
          checked={prefs.value.simple}
          onChange={(e) => setPrefs({ simple: (e.target as HTMLInputElement).checked })}
        />
        {t('ui.big_text_and_voice')}
      </label>

      <section class="privacy-notice">
        <h2>{t('ui.privacy_title')}</h2>
        <ul>
          <li>{t('ui.privacy_what_we_check')}</li>
          <li>{t('ui.privacy_nothing_kept')}</li>
          <li>{t('ui.privacy_forgotten_30min')}</li>
          <li>{t('ui.privacy_no_money_otp')}</li>
        </ul>
      </section>

      {installEvent.value && (
        <button
          type="button"
          class="btn"
          onClick={() => {
            void installEvent.value?.prompt();
            installEvent.value = null;
          }}
        >
          {t('ui.install_app')}
        </button>
      )}

      <button
        type="button"
        class="btn btn-primary btn-huge"
        onClick={() => {
          setPrefs({ onboarded: true });
          route('/');
        }}
      >
        {t('ui.continue')}
      </button>
    </main>
  );
}
