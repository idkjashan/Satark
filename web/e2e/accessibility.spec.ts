// Journey 14: axe on Home, Check, the verdict screen, a lesson and a simulator - zero
// serious/critical violations.
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { seedPrefs, submitCheck } from './helpers';

const SCAM_EN =
  'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). ' +
  'Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. ' +
  'Download app: https://tradeking-pro.in/app.apk';

async function expectNoSeriousViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  const summary = bad.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.map((n) => n.target.join(' ')),
  }));
  expect(summary, `axe found serious/critical violations:\n${JSON.stringify(summary, null, 2)}`).toEqual([]);
}

test('Home', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/');
  await expectNoSeriousViolations(page);
});

test('Check', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/check');
  await expectNoSeriousViolations(page);
});

test('the verdict screen', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, SCAM_EN);
  await expect(page.getByTestId('verdict-card')).toBeVisible({ timeout: 20_000 });
  await expectNoSeriousViolations(page);
});

test('a lesson', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/learn/compounding');
  await expectNoSeriousViolations(page);
});

test('a simulator', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/sim/S1');
  await expectNoSeriousViolations(page);
});
