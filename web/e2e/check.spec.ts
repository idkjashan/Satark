// Journeys 2-5: /check -> /run for an English scam, a genuine message, a Hindi scam, and the
// input-validation edge cases (empty / >4,000 chars). Plus one targeted regression test for the
// sim_params S2 pre-fill the lead added mid-session (verdict.sim_params -> /sim/S2?rate=&period=).
import { test, expect } from '@playwright/test';
import { seedPrefs, submitCheck, readIdbStore } from './helpers';

const SCAM_EN =
  'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). ' +
  'Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. ' +
  'Download app: https://tradeking-pro.in/app.apk';

const GENUINE_EN = 'Your SIP of ₹5,000 is due on 5 Oct. Never share your OTP with anyone.';

const SCAM_HI = 'रोज़ाना 3% मुनाफ़ा पक्का। VIP ग्रुप में जुड़ें। सीमित सीटें, आज ही जॉइन करें।';

test('English scam -> HIGH_RISK, <=3 reasons, tel:1930, explanation, a simulator link; history never stores the text', async ({
  page,
}) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });

  await test.step('submit and watch the live checklist', async () => {
    await submitCheck(page, SCAM_EN);
    await expect(page.getByTestId('checklist')).toBeVisible();
    await expect(page.locator('[data-testid^="checklist-row-"]').first()).toBeVisible();
  });

  await test.step('verdict card: HIGH_RISK with <=3 reasons', async () => {
    const card = page.getByTestId('verdict-card');
    await expect(card).toBeVisible({ timeout: 20_000 });
    await expect(card).toHaveAttribute('data-level', 'HIGH_RISK');
    const reasonCount = await page.getByTestId('reasons').locator('li').count();
    expect(reasonCount).toBeGreaterThan(0);
    expect(reasonCount).toBeLessThanOrEqual(3);
    // Source chips cite where a reason's evidence came from; not every reason code is DB-backed,
    // so this is informational (soft) rather than a hard requirement per reason.
    expect.soft(await card.locator('.source-chip').count(), 'expected at least one reason to cite a source').toBeGreaterThan(0);
  });

  await test.step('actions include a tel:1930 link', async () => {
    await expect(page.locator('a[href="tel:1930"]')).toBeVisible();
  });

  await test.step('explanation text is present', async () => {
    await expect(page.getByTestId('explanation')).not.toBeEmpty();
  });

  await test.step('"See how this trap works" opens a simulator', async () => {
    const link = page.getByRole('link', { name: 'See how this trap works' });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/sim\/S[123]/);
    await expect(page.locator('main.screen')).toBeVisible();
  });

  await test.step('history stores only the level, never the message text', async () => {
    await page.goto('/');
    await expect(page.getByText('Recent checks')).toBeVisible();
    const store = await readIdbStore(page);
    const dump = JSON.stringify(store);
    for (const secret of ['rajesh.profit', 'tradeking-pro', 'Suresh Mehta', 'INH000000002']) {
      expect(dump, `history must not contain ${secret}`).not.toContain(secret);
    }
    const history = store.history as Array<{ level: string }> | undefined;
    expect(history?.[0]?.level).toBe('HIGH_RISK');
    const rawLocalStorage = await page.evaluate(() => JSON.stringify(localStorage));
    expect(rawLocalStorage).not.toContain('rajesh.profit');
  });
});

test('genuine message -> NO_SIGNS, "No strong risk signs found", never claims it is safe', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, GENUINE_EN);

  const card = page.getByTestId('verdict-card');
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card).toHaveAttribute('data-level', 'NO_SIGNS');
  await expect(page.getByTestId('verdict-headline')).toContainText('No strong risk signs found');

  // The product never affirms safety (CONTRACTS §4 output guard: no "is safe" wording) - check
  // for that specific affirmative claim, not the bare word "safe" (the honest disclaimer "not the
  // same as safe" legitimately contains it and must not trip this check).
  const cardText = (await card.textContent()) ?? '';
  expect(cardText).not.toMatch(/\bis\s+safe\b|\bsafe\s+to\s+(pay|proceed|invest|trust|send)\b/i);
});

test('Hindi scam, no identifiers -> HIGH_RISK or SUSPICIOUS with a Hindi headline', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'hi' });
  await submitCheck(page, SCAM_HI);

  const card = page.getByTestId('verdict-card');
  await expect(card).toBeVisible({ timeout: 20_000 });
  const level = await card.getAttribute('data-level');
  expect(['HIGH_RISK', 'SUSPICIOUS']).toContain(level);

  const expectedHeadline =
    level === 'HIGH_RISK' ? 'ज़्यादा ख़तरा — पैसे न भेजें' : 'शक है — कार्रवाई से पहले जाँच लें';
  await expect(page.getByTestId('verdict-headline')).toContainText(expectedHeadline);
});

test.describe('input validation', () => {
  test('empty input -> a clear error, no navigation away from /check', async ({ page }) => {
    await seedPrefs(page, { lang: 'en' });
    await page.goto('/check');
    await page.getByTestId('check-submit').click();
    await expect(page.getByRole('alert')).toHaveText('Please paste a message or add a screenshot first.');
    await expect(page).toHaveURL(/\/check$/);
  });

  test('>4,000 chars -> the API error message, in the UI language', async ({ page }) => {
    await seedPrefs(page, { lang: 'en' });
    await page.goto('/check');
    await page.getByTestId('check-input').fill('a'.repeat(4001));
    await page.getByTestId('check-submit').click();
    await expect(page.getByRole('alert')).toHaveText('This is too large. Please share something smaller.', {
      timeout: 20_000,
    });
    await expect(page).toHaveURL(/\/check$/);
  });
});

test('a "5% daily" promise opens the S2 calculator pre-filled with that rate (sim_params)', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, 'Guaranteed 5% daily profit, join our VIP group');

  const card = page.getByTestId('verdict-card');
  await expect(card).toBeVisible({ timeout: 20_000 });

  const link = page.getByRole('link', { name: 'See how this trap works' });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute('href', '/sim/S2?rate=5&period=day');
  await link.click();
  await expect(page).toHaveURL(/\/sim\/S2\?rate=5&period=day/);
  await expect(page.getByLabel('Promised rate (%)')).toHaveValue('5');
});
