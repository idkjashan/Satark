// Journey 13: offline-first. The service worker (src/sw.ts) precaches the app shell on install
// and claims the page immediately (skipWaiting + clients.claim, no reload needed), so after one
// online load, the shell, a lesson and a simulator should all still work with no network at all.
import { test, expect } from '@playwright/test';
import { seedPrefs } from './helpers';

test('after one load, offline: the shell, a lesson and a simulator work; a check fails kindly', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });

  await page.goto('/');
  await expect(page.getByTestId('home-check')).toBeVisible();
  // Wait for the SW to install, precache (its install handler's waitUntil) and claim this page -
  // not just "registered", or the very next offline navigation would have nothing to fall back to.
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null, { timeout: 20_000 });

  await page.context().setOffline(true);

  await test.step('app shell: a fresh full navigation to Home still renders', async () => {
    await page.goto('/');
    await expect(page.getByTestId('home-check')).toBeVisible();
  });

  await test.step('a lesson still works offline', async () => {
    await page.goto('/learn/compounding');
    await expect(page.getByTestId('lesson-next')).toBeVisible();
  });

  await test.step('a simulator still works offline', async () => {
    await page.goto('/sim/S2');
    await expect(page.getByLabel('Promised rate (%)')).toBeVisible();
  });

  await test.step('a check shows a friendly message, not a blank screen', async () => {
    await page.goto('/check');
    await page.getByTestId('check-input').fill('anything');
    await page.getByTestId('check-submit').click();
    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).not.toBeEmpty();
    await expect(page.getByTestId('check-input')).toBeVisible(); // the screen itself is intact
  });
});
