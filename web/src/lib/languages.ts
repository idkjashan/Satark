// Shared "enabled languages" signal (CONTRACTS §6 `GET /v1/meta` -> languages). Onboarding,
// Settings and the header language switcher all need this same list with the same static
// en/hi fallback - one fetch-once signal instead of three copies of the same try/catch.
import { signal } from '@preact/signals';
import { getMeta } from './api';
import { FALLBACK_LANGUAGES } from './i18n';

export const enabledLanguages = signal(FALLBACK_LANGUAGES);

let requested = false;

/** Fetches once per page load; safe to call from every component that needs the list. */
export function ensureLanguagesLoaded(): void {
  if (requested) return;
  requested = true;
  void getMeta()
    .then((meta) => {
      if (meta.languages?.length) enabledLanguages.value = meta.languages;
    })
    .catch(() => {
      // offline or the API isn't up yet - the static fallback list is enough
    });
}
