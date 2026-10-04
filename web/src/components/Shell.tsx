// App chrome, rendered once around the router (design v2, Oct 2026): a header with a contextual back
// button or the brand, a language switcher and a settings gear; a nav that is a bottom tab bar below
// 1024px and a left sidebar (brand on top, Settings at the bottom) from 1024px up - one set of
// markup, CSS repositions it (see styles.css ".app-nav"); an offline banner. Home, Check, Ask, Learn and
// Practice are the five tabs (product spec) - everything else (Settings, About data, History) is
// one tap from Home's footer, so nothing in the app is more than two taps from Home.
import type { ComponentChildren } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs, setPrefs } from '../lib/signals';
import { enabledLanguages, ensureLanguagesLoaded } from '../lib/languages';
import { Icon, type IconName } from './Icon';
import { Shield } from './Shield';

const TABS: { path: string; labelKey: string; icon: IconName; match: (p: string) => boolean }[] = [
  { path: '/', labelKey: 'ui.nav_home', icon: 'home', match: (p) => p === '/' },
  { path: '/check', labelKey: 'ui.nav_check', icon: 'check', match: (p) => p === '/check' || p.startsWith('/run/') },
  { path: '/chat/new', labelKey: 'ui.nav_ask', icon: 'chat', match: (p) => p.startsWith('/chat') },
  { path: '/learn', labelKey: 'ui.nav_learn', icon: 'learn', match: (p) => p.startsWith('/learn') },
  { path: '/practice', labelKey: 'ui.nav_practice', icon: 'practice', match: (p) => p.startsWith('/practice') || p.startsWith('/sim/') },
];

// Exact tab-root paths never show a back button - the tab bar / sidebar is already "home enough".
// Everything reached one level deeper (a run, a lesson, a sim, Settings, About data, History...)
// gets one, since a standalone PWA window has no browser chrome back button of its own.
const TAB_ROOTS = new Set(['/', '/check', '/chat', '/learn', '/practice']);

function useOnline(): boolean {
  const [online, setOnline] = useState(() => typeof navigator === 'undefined' || navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}

export function Shell({ children }: { children: ComponentChildren }) {
  const { path, route } = useLocation();
  const online = useOnline();

  useEffect(() => ensureLanguagesLoaded(), []);

  const showBack = !TAB_ROOTS.has(path);

  function goBack(e: Event) {
    e.preventDefault();
    if (typeof window !== 'undefined' && window.history.length > 1) window.history.back();
    else route('/');
  }

  return (
    <div class="app-shell">
      <a class="skip-link" href="#main-content">
        {t('ui.skip_to_content')}
      </a>

      <header class="app-header">
        {showBack ? (
          <button type="button" class="back-btn" onClick={goBack}>
            <Icon name="back" />
            <span>{t('ui.back')}</span>
          </button>
        ) : (
          <a class="brand brand-header" href="/">
            <Shield size={32} />
            <span class="brand-name">Satark</span>
          </a>
        )}

        <div class="header-spacer" />

        <label class="lang-switch">
          <Icon name="globe" />
          <span class="visually-hidden">{t('ui.switch_language')}</span>
          <select
            aria-label={t('ui.switch_language')}
            value={prefs.value.lang}
            onChange={(e) => setPrefs({ lang: (e.target as HTMLSelectElement).value })}
          >
            {enabledLanguages.value.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.native}
              </option>
            ))}
          </select>
        </label>

        <a class="icon-btn header-settings" href="/settings" aria-label={t('ui.settings')} aria-current={path === '/settings' ? 'page' : undefined}>
          <Icon name="settings" size={20} />
        </a>
      </header>

      {!online && (
        <p class="offline-banner" role="status">
          <Icon name="wifiOff" />
          {t('ui.offline_banner')}
        </p>
      )}

      <div class="app-body">
        <nav class="app-nav" aria-label={t('ui.nav_main')}>
          <div class="brand brand-side" aria-hidden="true">
            <Shield size={36} />
            <span class="brand-name">Satark</span>
          </div>
          {TABS.map((tab) => {
            const active = tab.match(path);
            return (
              <a key={tab.path} href={tab.path} class={`app-nav-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>
                <Icon name={tab.icon} size={22} />
                <span>{t(tab.labelKey)}</span>
              </a>
            );
          })}
          <a href="/settings" class={`app-nav-item nav-settings ${path === '/settings' ? 'active' : ''}`}>
            <Icon name="settings" size={22} />
            <span>{t('ui.settings')}</span>
          </a>
        </nav>

        <div id="main-content" class="app-main">
          {children}
        </div>
      </div>
    </div>
  );
}
