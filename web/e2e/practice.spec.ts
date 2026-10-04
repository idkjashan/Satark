// Journey 8: Practice -> S1 (fake trading-app FSM), S2 (returns calculator), S3 (leverage wipe-out).
import { test, expect } from '@playwright/test';
import { seedPrefs } from './helpers';

test('S1: join -> pay -> withdraw -> blocked -> keep paying -> an end screen with the lesson rule and a loss in en-IN', async ({
  page,
}) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/sim/S1');

  await page.getByTestId('sim-choice-join').click(); // invite -> deposit
  await page.getByTestId('sim-choice-pay').click(); // deposit -> profits (lost=10000)
  await page.getByTestId('sim-choice-withdraw').click(); // profits -> blocked
  await page.getByTestId('sim-choice-pay_tax').click(); // blocked -> unlock (lost=22600)
  // "unlock" is one more fee screen, not an end state yet; keep paying through to the end,
  // matching the task's "...withdraw blocked -> pay tax" path to its actual terminal screen.
  await page.getByTestId('sim-choice-pay_fee').click(); // unlock -> lost_all (lost=34600)

  const end = page.getByTestId('sim-end');
  await expect(end).toBeVisible();
  await expect(end).toContainText('always means it is a scam'); // the lesson rule
  await expect(page.getByTestId('sim-balance')).toHaveText('You lost ₹34,600'); // en-IN grouping
});

test('S2: a 1%-a-day promise projects to roughly 12x in a year', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/sim/S2');

  await page.getByLabel('Promised rate (%)').fill('1');
  await page.getByLabel('Period').selectOption('day');
  await page.getByLabel('Amount').fill('10000');

  const afterOneYear = page.locator('li', { hasText: 'After 1 year' }).locator('strong');
  await expect(afterOneYear).toBeVisible();
  const text = (await afterOneYear.innerText()).trim(); // e.g. "₹1.2 lakh"
  const match = /₹([\d.]+)\s*lakh/.exec(text);
  expect(match, `expected a lakh-formatted amount, got "${text}"`).not.toBeNull();
  const rupees = Number(match![1]) * 100_000;
  // 10,000 * 1.01^250 (250 trading days/year, CONTRACTS §7.3) ~= 1,20,297 - roughly 12x principal.
  expect(rupees).toBeGreaterThan(110_000);
  expect(rupees).toBeLessThan(130_000);
  // content/sims/S2.json's own texts.impossible overrides the generic ui.no_one_can_promise_this
  // fallback - this is the real, always-visible warning line (S2Player renders it unconditionally).
  await expect(page.getByText('No investment can promise this.')).toBeVisible();
});

test('S3: advancing the leverage simulator reaches a margin call or wipe-out', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/sim/S3');

  await expect(page.getByRole('heading', { name: 'The leverage wipe-out' })).toBeVisible();
  // The default 8x (content/sims/S3.json) never dips below a margin call with this seed over 30
  // steps (verified: min equity ~5,300 of a 10,000 margin) - push the slider to its max (10x, the
  // one lever the UI actually gives a user) to reach the outcome this simulator exists to teach.
  await page.getByLabel(/Leverage/).focus();
  await page.getByLabel(/Leverage/).press('End');
  await page.getByRole('button', { name: 'Start' }).click();

  let sawMarginOrWipeout = false;
  for (let i = 0; i <= 30; i++) {
    const status = (await page.locator('.sim-status').innerText()).trim();
    if (status === 'Margin call' || status === 'Wiped out') sawMarginOrWipeout = true;
    if (await page.getByTestId('sim-end').isVisible()) break;
    await page.getByRole('button', { name: 'Next' }).click();
  }
  expect(sawMarginOrWipeout, 'expected the seeded path to hit a margin call or wipe-out within 30 steps').toBe(true);
  await expect(page.getByTestId('sim-end')).toBeVisible();
});
