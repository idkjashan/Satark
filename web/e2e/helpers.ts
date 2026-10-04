// Shared helpers for the Satark E2E suite. Kept as plain functions (no custom fixtures) - every
// spec already gets an isolated browser context (and thus isolated localStorage/IndexedDB) from
// Playwright's default `page` fixture, so there is nothing more to wire up.
import type { Page } from '@playwright/test';

export interface PrefsPatch {
  lang?: string;
  simple?: boolean;
  textSize?: 'normal' | 'large';
  theme?: 'auto' | 'light' | 'dark';
  onboarded?: boolean;
}

const DEFAULT_PREFS = {
  lang: 'en',
  voice: '',
  rate: 1,
  textSize: 'normal',
  simple: false,
  theme: 'auto',
  onboarded: false,
};

/**
 * Seeds localStorage's `prefs` key via an init script, which runs before any page script on
 * every subsequent navigation in this context - so Onboarding is skipped from the very first
 * paint (signals.ts reads prefs synchronously at module load). Defaults to onboarded:true since
 * most journeys are not testing onboarding itself (that is journey 1, which calls the real flow).
 */
export async function seedPrefs(page: Page, patch: PrefsPatch = {}): Promise<void> {
  const prefs = { ...DEFAULT_PREFS, onboarded: true, ...patch };
  await page.addInitScript((p) => {
    localStorage.setItem('prefs', JSON.stringify(p));
  }, prefs);
}

/** Every key/value in idb-keyval's default store (db "keyval-store", object store "keyval"). */
export async function readIdbStore(page: Page): Promise<Record<string, unknown>> {
  return page.evaluate(
    () =>
      new Promise<Record<string, unknown>>((resolve, reject) => {
        const req = indexedDB.open('keyval-store');
        req.onerror = () => reject(req.error);
        req.onsuccess = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains('keyval')) {
            resolve({});
            return;
          }
          const store = db.transaction('keyval', 'readonly').objectStore('keyval');
          const out: Record<string, unknown> = {};
          const cursorReq = store.openCursor();
          cursorReq.onsuccess = () => {
            const cursor = cursorReq.result;
            if (cursor) {
              out[String(cursor.key)] = cursor.value;
              cursor.continue();
            } else resolve(out);
          };
          cursorReq.onerror = () => reject(cursorReq.error);
        };
      }),
  );
}

/** Navigates to /check, fills the textarea and submits; waits for the /run/:id redirect. */
export async function submitCheck(page: Page, text: string): Promise<void> {
  await page.goto('/check');
  await page.getByTestId('check-input').fill(text);
  await page.getByTestId('check-submit').click();
  await page.waitForURL(/\/run\//, { timeout: 20_000 });
}
