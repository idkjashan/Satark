// Journey 6: "Ask or learn" from Home with no prior case (content/faq.json answers it, since the
// deterministic server has no LLM configured - CONTRACTS §7.4/§6.1 "Without a model, chat answers
// come from content/faq.json or chat.fallback").
import { test, expect } from '@playwright/test';
import { seedPrefs } from './helpers';

test('ask "What is SIP?" from Home -> an answer with a lesson action and a tappable chip', async ({ page }) => {
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/');

  await page.getByRole('link', { name: 'Ask a question' }).click();
  await expect(page).toHaveURL(/\/chat\/new/);
  await expect(page.getByTestId('chat-screen')).toBeVisible();

  await page.getByTestId('chat-input').fill('What is SIP?');
  await page.getByTestId('chat-send').click();

  const firstAnswer = page.getByTestId('chat-answer').first();
  await expect(firstAnswer).toContainText('SIP', { timeout: 20_000 });
  await expect(page.getByTestId('action-lesson_compounding')).toBeVisible();

  const chip = page.getByRole('button', { name: 'Guaranteed returns?' });
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(page.getByTestId('chat-answer')).toHaveCount(2, { timeout: 20_000 });

  // Mic: disclosed (button + the "may send your voice to Google" notice) when this browser
  // supports dictation, hidden entirely otherwise (Check.tsx/Chat.tsx share isDictationSupported()).
  const dictationSupported = await page.evaluate(() => 'webkitSpeechRecognition' in window);
  if (dictationSupported) {
    await expect(page.locator('button.btn-mic')).toBeVisible();
    await expect(page.getByText('Your browser may send your voice to Google')).toBeVisible();
  } else {
    await expect(page.locator('button.btn-mic')).toHaveCount(0);
  }
});

test('BUG repro: "What is a SIP?" (the task\'s own example phrasing) does not match the SIP FAQ intent', async ({
  page,
}) => {
  // content/faq.json's learn_sip intent only lists the pattern "what is sip" (plus Hinglish/Hindi
  // variants) - a natural "what is A sip" never contains that substring, so the deterministic
  // matcher (satark/harness/respond.py _faq_answer: `pattern in message.lower()`) falls through to
  // the generic fallback instead of the SIP lesson. Content bug (content/faq.json, owned by G) -
  // left failing on purpose as the exact repro; not mine to edit (see CONTRACTS §1 ownership).
  test.setTimeout(45_000);
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/chat/new');
  await page.getByTestId('chat-input').fill('What is a SIP?');
  await page.getByTestId('chat-send').click();
  await expect(page.getByTestId('chat-answer').first()).toContainText('SIP', { timeout: 20_000 });
});
