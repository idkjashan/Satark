// Journey 10: Settings - switch language to English and back; "Clear my data" empties history.
import { test, expect } from '@playwright/test';
import { seedPrefs, submitCheck, readIdbStore } from './helpers';

const GENUINE_EN = 'Your SIP of ₹5,000 is due on 5 Oct. Never share your OTP with anyone.';

test('switch language to English and back', async ({ page }) => {
  await seedPrefs(page, { lang: 'hi' });
  await page.goto('/settings');

  await expect(page.getByRole('heading', { name: 'सेटिंग्स' })).toBeVisible();

  // Scoped to the page body, not just getByLabel('भाषा'): the shell header (every screen, Oct
  // 2026 nav redesign) added its own quick language switcher, whose Hindi label "भाषा बदलें"
  // ("switch language") legitimately contains "भाषा" too - two controls on the page can now
  // change the language, so the settings-page one (full word/scope semantics) needs scoping to
  // stay unambiguous. The language select's own label is itself translated, so it reads "भाषा"
  // until switched.
  const settingsScreen = page.locator('.settings-screen');
  await settingsScreen.getByLabel('भाषा').selectOption('en');
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();

  await settingsScreen.getByLabel('Language').selectOption('hi');
  await expect(page.getByRole('heading', { name: 'सेटिंग्स' })).toBeVisible();
});

test('"Clear my data" empties history', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });

  await submitCheck(page, GENUINE_EN);
  await expect(page.getByTestId('verdict-card')).toBeVisible({ timeout: 20_000 });

  await page.goto('/');
  await expect(page.getByText('Recent checks')).toBeVisible();
  const before = (await readIdbStore(page)).history as unknown[] | undefined;
  expect(before?.length ?? 0).toBeGreaterThan(0);

  await page.goto('/settings');
  await page.getByRole('button', { name: 'Clear my data' }).click();
  await expect(page.getByRole('status')).toHaveText('Your data has been cleared.');

  const after = (await readIdbStore(page)).history as unknown[] | undefined;
  expect(after ?? []).toHaveLength(0);

  // seedPrefs re-seeds `onboarded` on every navigation in this context, so this still lands
  // on Home (not re-onboarding) even though Settings' own reset cleared localStorage - exactly
  // what lets us observe the history section disappear rather than just the IndexedDB key.
  await page.goto('/');
  await expect(page.getByText('Recent checks')).toHaveCount(0);
});
