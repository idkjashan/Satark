// /settings (LLD §21.2/§21.3): language, text size, voice speed, Simple mode, a trusted family
// contact (phone-only, never leaves the device), and "Clear my data".
import { useEffect } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { t } from '../lib/i18n';
import { prefs, setPrefs, resetPrefs } from '../lib/signals';
import { enabledLanguages, ensureLanguagesLoaded } from '../lib/languages';
import { getFamily, setFamily, clearAllData, type Family } from '../lib/idb';
import { clearAllMissed } from '../lib/retest';

export function Settings() {
  const family = useSignal<Family>({});
  const cleared = useSignal(false);

  useEffect(() => {
    void getFamily().then((f) => (family.value = f));
    ensureLanguagesLoaded();
  }, []);

  return (
    <main class="screen settings-screen">
      <header class="page-head">
        <h1>{t('ui.settings')}</h1>
      </header>

      <section class="card settings-group">
      <h2 class="section-label">{t('ui.settings_display')}</h2>
      <label class="settings-row">
        {t('ui.language')}
        <select value={prefs.value.lang} onChange={(e) => setPrefs({ lang: (e.target as HTMLSelectElement).value })}>
          {enabledLanguages.value.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.native}
            </option>
          ))}
        </select>
      </label>

      <label class="settings-row">
        {t('ui.theme')}
        <select
          value={prefs.value.theme}
          onChange={(e) => setPrefs({ theme: (e.target as HTMLSelectElement).value as 'auto' | 'light' | 'dark' })}
        >
          <option value="auto">{t('ui.theme_auto')}</option>
          <option value="light">{t('ui.theme_light')}</option>
          <option value="dark">{t('ui.theme_dark')}</option>
        </select>
      </label>

      <label class="settings-row">
        {t('ui.text_size')}
        <select
          value={prefs.value.textSize}
          onChange={(e) => setPrefs({ textSize: (e.target as HTMLSelectElement).value as 'normal' | 'large' })}
        >
          <option value="normal">{t('ui.text_size_normal')}</option>
          <option value="large">{t('ui.text_size_large')}</option>
        </select>
      </label>

      </section>

      <section class="card settings-group">
      <h2 class="section-label">{t('ui.settings_voice')}</h2>
      <label class="settings-row">
        {t('ui.voice_speed')}
        <input
          type="range"
          min={0.7}
          max={1.3}
          step={0.1}
          value={prefs.value.rate}
          onInput={(e) => setPrefs({ rate: Number((e.target as HTMLInputElement).value) })}
        />
      </label>

      <label class="settings-row settings-check">
        <input
          type="checkbox"
          data-testid="simple-toggle"
          checked={prefs.value.simple}
          onChange={(e) => setPrefs({ simple: (e.target as HTMLInputElement).checked })}
        />
        {t('ui.big_text_and_voice')}
      </label>

      </section>

      <section class="card settings-group">
      <fieldset class="settings-row">
        <legend>{t('ui.trusted_contact')}</legend>
        <input
          type="text"
          placeholder={t('ui.contact_name')}
          value={family.value.name ?? ''}
          onInput={(e) => {
            family.value = { ...family.value, name: (e.target as HTMLInputElement).value };
            void setFamily(family.value);
          }}
        />
        <input
          type="tel"
          placeholder={t('ui.contact_phone')}
          value={family.value.phone ?? ''}
          onInput={(e) => {
            family.value = { ...family.value, phone: (e.target as HTMLInputElement).value };
            void setFamily(family.value);
          }}
        />
      </fieldset>

      <h2 class="section-label">{t('ui.settings_data')}</h2>
      <button
        type="button"
        class="btn btn-danger"
        onClick={async () => {
          await clearAllData();
          resetPrefs();
          clearAllMissed();
          family.value = {};
          cleared.value = true;
        }}
      >
        {t('ui.clear_my_data')}
      </button>
      {cleared.value && <p role="status">{t('ui.data_cleared')}</p>}
      </section>
    </main>
  );
}
