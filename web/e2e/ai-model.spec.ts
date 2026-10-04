// Journey 15 (AI-model server, project "mobile-ai" -> baseURL :8101, mock LLM on :9101 -
// scripts/mock_llm.py, read its docstring for exactly what it does and why).
import { test, expect } from '@playwright/test';
import { seedPrefs, submitCheck } from './helpers';

const SCAM_EN =
  'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). ' +
  'Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. ' +
  'Download app: https://tradeking-pro.in/app.apk';
const OFF_TOPIC_CODE_REQUEST = 'Write a Python function to reverse a string';

test('chat: an off-topic coding request gets a polite refusal, no code shown', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/chat/new');
  await page.getByTestId('chat-input').fill(OFF_TOPIC_CODE_REQUEST);
  await page.getByTestId('chat-send').click();

  const answer = page.getByTestId('chat-answer').first();
  await expect(answer).toContainText('I can only help with money safety', { timeout: 20_000 });
  const text = (await answer.innerText()).toLowerCase();
  expect(text).not.toContain('```');
  expect(text).not.toContain('def reverse');
  await expect(page.getByText('Satark helps with money safety and learning.')).toBeVisible();
});

test('chat: "What is a SIP?" gets a real answer from the model', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/chat/new');
  await page.getByTestId('chat-input').fill('What is a SIP?');
  await page.getByTestId('chat-send').click();

  await expect(page.getByTestId('chat-answer').first()).toContainText('systematic investment plan', {
    timeout: 20_000,
    ignoreCase: true,
  });
});

test('check: the English scam still gets a verdict and an explanation with the model wired up', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, SCAM_EN);

  const card = page.getByTestId('verdict-card');
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card).toHaveAttribute('data-level', 'HIGH_RISK');
  await expect(page.getByTestId('explanation')).not.toBeEmpty();
});

test('check: an off-topic coding request gets the off-topic note with a "Check another message" button', async ({
  page,
}) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, OFF_TOPIC_CODE_REQUEST);

  const askUser = page.getByTestId('ask-user');
  await expect(askUser).toBeVisible({ timeout: 20_000 });
  const checkAnother = askUser.getByRole('link', { name: 'Check another message' });
  await expect(checkAnother).toHaveAttribute('href', '/check');
});
