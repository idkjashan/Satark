// Journey 11: About data - sources with "as on" dates, straight from GET /v1/meta.
import { test, expect } from '@playwright/test';
import { seedPrefs } from './helpers';

test('About this data renders sources with an "as on" date from /v1/meta', async ({ page, request, baseURL }) => {
  const meta = await (await request.get(`${baseURL}/v1/meta`)).json();
  expect(Array.isArray(meta.sources) && meta.sources.length).toBeTruthy();
  const withDate = meta.sources.find((s: { as_on?: string | null }) => s.as_on);
  expect(withDate, 'expected at least one source with an as_on date to assert against').toBeTruthy();

  await seedPrefs(page, { lang: 'en' });
  await page.goto('/about-data');

  await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible();
  const expectedDate = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(
    new Date(withDate.as_on),
  );
  const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  await expect(page.getByText(new RegExp(`${escapeRe(withDate.name)}.*${escapeRe(expectedDate)}`))).toBeVisible();
  await expect(page.getByText(`Version: ${meta.version}`)).toBeVisible();
});
