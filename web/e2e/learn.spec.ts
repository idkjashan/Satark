// Journey 7: Learn -> a lesson -> step through with Next -> quiz -> progress marked done.
import { test, expect } from '@playwright/test';
import { seedPrefs, readIdbStore } from './helpers';

test('open a lesson, step through with Next, answer the quiz; Learn then shows it done', async ({ page }) => {
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/learn');
  await page.getByRole('link', { name: 'Why "1% a day" is impossible' }).click();
  await expect(page).toHaveURL(/\/learn\/compounding/);

  // Content-agnostic: click Next until the quiz appears, rather than hardcoding the step count.
  for (let i = 0; i < 10 && !(await page.getByTestId('lesson-quiz').isVisible()); i++) {
    await page.getByTestId('lesson-next').click();
  }
  await expect(page.getByTestId('lesson-quiz')).toBeVisible();

  await page.getByTestId('quiz-option-a').click(); // "About 12 times" - the correct option
  await expect(page.getByTestId('quiz-option-a')).toHaveClass(/correct/);
  await expect(page.getByText('No one can guarantee a daily return')).toBeVisible();

  await page.getByRole('link', { name: 'Done' }).click();
  await expect(page).toHaveURL(/\/learn$/);

  const progress = (await readIdbStore(page)).progress as { lessons?: Record<string, { done?: boolean }> } | undefined;
  expect(progress?.lessons?.compounding?.done).toBe(true);
  await expect(page.locator('a.lesson-row', { hasText: 'Why "1% a day" is impossible' })).toContainText('✓');
});
