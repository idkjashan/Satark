// Journey 1: first launch -> onboarding -> Home in Hindi.
import { test, expect } from '@playwright/test';

test('choose Hindi, see the privacy notice, enable Simple mode, land on a Hindi Home', async ({ page }) => {
  // No seedPrefs: a brand-new context has no `prefs` key at all, i.e. true first launch
  // (DEFAULT_PREFS.onboarded === false), so app.tsx renders Onboarding for any path.
  await page.goto('/');

  await expect(page.getByTestId('lang-hi')).toBeVisible();
  await page.getByTestId('lang-hi').click();
  await expect(page.getByTestId('lang-hi')).toHaveAttribute('aria-pressed', 'true');

  // Privacy notice (ui.privacy_title + its four bullet keys) is on the same screen.
  await expect(page.getByRole('heading', { name: 'आपकी प्राइवेसी' })).toBeVisible();
  await expect(page.locator('.privacy-notice li')).toHaveCount(4);

  // Enable "Big text and voice?" (Simple mode).
  const simpleToggle = page.getByTestId('simple-toggle');
  await expect(simpleToggle).not.toBeChecked();
  await simpleToggle.check();
  await expect(simpleToggle).toBeChecked();

  await page.getByRole('button', { name: 'आगे बढ़ें' }).click();

  // Home, in Hindi, both primary actions present.
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId('home-check')).toHaveText('मैसेज जाँचें');
  await expect(page.getByText('पूछें या सीखें')).toBeVisible();
  await expect(page.getByTestId('home-learn')).toHaveText('सीखें');
  await expect(page.getByTestId('home-practice')).toHaveText('अभ्यास');
  await expect(page.getByTestId('home-help')).toHaveText('मैंने पैसे भेज दिए — मदद करें');
  await expect(page.getByText('कोई विज्ञापन नहीं। कोई टिप नहीं। हम कभी पैसे या OTP नहीं माँगते।')).toBeVisible();

  // Simple mode persisted onto <html> (drives the 20px base / auto-speak behaviour).
  await expect(page.locator('html')).toHaveClass(/simple/);
  await expect(page.locator('html')).toHaveAttribute('lang', 'hi');
});
