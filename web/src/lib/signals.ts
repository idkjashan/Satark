// Preferences store (LLD §21.3): localStorage, read synchronously before first paint so
// <html lang> and the `simple` class are correct before Preact renders anything.
// Run and simulator state are component-local signals (useSignal in Run.tsx / SimPlayer.tsx) -
// nothing else in the app needs to read them, so a global store would just be more surface area.
import { signal } from '@preact/signals';

export interface Prefs {
  lang: string;
  voice: string; // speechSynthesis voiceURI; '' = auto-pick the best match for `lang`
  rate: number; // speechSynthesis rate, ~0.8-1.3
  textSize: 'normal' | 'large';
  simple: boolean; // "Big text and voice?" - 20px base, auto-speak verdicts
  theme: 'auto' | 'light' | 'dark'; // 'auto' follows prefers-color-scheme (Settings toggle)
  onboarded: boolean;
}

export const DEFAULT_PREFS: Prefs = {
  lang: 'en',
  voice: '',
  rate: 1,
  textSize: 'normal',
  simple: false,
  theme: 'auto',
  onboarded: false,
};

const STORAGE_KEY = 'prefs';

function readPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    return { ...DEFAULT_PREFS }; // storage unavailable (private mode) - run in memory only
  }
}

export const prefs = signal<Prefs>(readPrefs());

/** Mirrors lang/simple/textSize/theme onto <html> so CSS and `lang` apply without a re-render.
 * `theme` 'auto' removes the attribute entirely so the plain `prefers-color-scheme` media query
 * in styles.css decides - only 'light'/'dark' set an explicit override (Settings dark-mode toggle). */
export function applyPrefsToDocument(p: Prefs = prefs.value): void {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = p.lang;
  document.documentElement.classList.toggle('simple', p.simple);
  document.documentElement.classList.toggle('text-large', p.textSize === 'large');
  if (p.theme === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', p.theme);
}

export function setPrefs(patch: Partial<Prefs>): void {
  prefs.value = { ...prefs.value, ...patch };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs.value));
  } catch {
    // quota or private mode - the signal still updates for this session
  }
  applyPrefsToDocument(prefs.value);
}

/** "Clear my data" (Settings): back to defaults, not onboarding again mid-session. */
export function resetPrefs(): void {
  prefs.value = { ...DEFAULT_PREFS, onboarded: true, lang: prefs.value.lang };
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  applyPrefsToDocument(prefs.value);
}
