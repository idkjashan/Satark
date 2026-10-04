// Journey 9: "I already paid - help". Answering the three questions and generating the complaint
// text calls the REAL POST /v1/report-draft for the case just checked in this same session
// (lastCaseId, kept in memory by api.ts), so the draft pulls that case's own evidence - including
// the scammer's UPI ID, unmasked (CONTRACTS §7.1 report.involved_row; satark/harness/report.py).
import { test, expect } from '@playwright/test';
import { seedPrefs, submitCheck } from './helpers';

const SCAM_EN =
  'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). ' +
  'Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. ' +
  'Download app: https://tradeking-pro.in/app.apk';

test('answer the three questions -> numbered steps, tel:1930, a copyable draft with this case\'s UPI ID', async ({
  page,
}) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });

  // A check first, in the same page/session, so lastCaseId is populated (api.ts keeps it in
  // memory only - a fresh page would not have it, which is also exactly why history never does).
  // Reaching /help-paid is via the verdict card's own link (an in-app <a>, intercepted by
  // preact-iso), not page.goto: a hard navigation would reload the document and lose that
  // in-memory case id, same as a user typing the URL - there is no other in-app path today (see
  // the fix note in VerdictCard.tsx).
  await submitCheck(page, SCAM_EN);
  await expect(page.getByTestId('verdict-card')).toHaveAttribute('data-level', 'HIGH_RISK', { timeout: 20_000 });
  await page.getByRole('link', { name: 'I already paid' }).click();
  await expect(page).toHaveURL(/\/help-paid/);

  await expect(page.getByTestId('help-step-1').getByRole('link', { name: 'Call 1930 now' })).toHaveAttribute(
    'href',
    'tel:1930',
  );
  await expect(page.getByTestId('help-step-2')).toBeVisible();
  await expect(page.getByTestId('help-step-3').getByRole('link')).toHaveAttribute('href', 'https://cybercrime.gov.in');
  await expect(page.getByTestId('help-step-4')).toBeVisible();

  await page.getByLabel('Today').check();
  await page.getByLabel('UPI', { exact: true }).check();
  await page.getByLabel('₹10,000 – ₹1,00,000').check();

  await page.getByRole('button', { name: 'Prepare complaint text' }).click();
  const draft = page.locator('textarea[readonly]');
  await expect(draft).toHaveValue(/rajesh\.profit@okaxis/, { timeout: 20_000 });

  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.getByRole('button', { name: 'Copy', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Copied!' })).toBeVisible();
});
