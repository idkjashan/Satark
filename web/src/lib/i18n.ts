// i18n (CONTRACTS §7.1): t(key, vars) over merged ui.<lang>.json (ours) + content.<lang>.json
// (engineer G's, written in parallel - may be empty or missing keys right now).
// Lookup order per key: current language -> English -> the key itself, so a missing translation
// is visible (shows the key) instead of crashing or showing "undefined".
import { prefs } from './signals';

export type Dict = Record<string, string>;

/** Pure: {en: {...}, hi: {...}} + current lang + key -> text. Exported so tests don't need the glob. */
export function resolveKey(dicts: Record<string, Dict>, lang: string, key: string): string {
  return dicts[lang]?.[key] ?? dicts.en?.[key] ?? key;
}

/** Pure: "{name} lost {amount}" + {name:"Raj", amount:"₹1,000"} -> "Raj lost ₹1,000". */
export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}

function langOf(globKey: string): string {
  const m = /\.([a-zA-Z]{2,3})\.json$/.exec(globKey);
  return m ? m[1].toLowerCase() : 'en';
}

function mergeByLang(modules: Record<string, Dict>): Record<string, Dict> {
  const out: Record<string, Dict> = {};
  for (const [path, dict] of Object.entries(modules)) {
    const lang = langOf(path);
    out[lang] = { ...out[lang], ...dict };
  }
  return out;
}

// Ours: always present. G's: may not exist yet for any language - glob just yields {}.
const uiModules = import.meta.glob<Dict>('../../../content/i18n/ui.*.json', { eager: true, import: 'default' });
const contentModules = import.meta.glob<Dict>('@content/i18n/content.*.json', { eager: true, import: 'default' });

const uiByLang = mergeByLang(uiModules as unknown as Record<string, Dict>);
const contentByLang = mergeByLang(contentModules as unknown as Record<string, Dict>);

const allLangs = new Set([...Object.keys(uiByLang), ...Object.keys(contentByLang)]);
const merged: Record<string, Dict> = {};
for (const lang of allLangs) {
  merged[lang] = { ...(contentByLang[lang] ?? {}), ...(uiByLang[lang] ?? {}) };
}

export function t(key: string, vars?: Record<string, string | number>): string {
  return interpolate(resolveKey(merged, prefs.value.lang || 'en', key), vars);
}

/** Static fallback for /onboarding before GET /v1/meta answers (or if it never does). */
export const FALLBACK_LANGUAGES = [
  { code: 'en', name: 'English', native: 'English', speech: 'en-IN' },
  { code: 'hi', name: 'Hindi', native: 'हिन्दी', speech: 'hi-IN' },
];
