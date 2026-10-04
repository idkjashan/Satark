// Journey 12: the share-target fallback for when the service worker didn't intercept the Web
// Share Target POST (satark/api/share.py) - a plain multipart POST, a 303, then the PWA reading
// `?text=` (Check.tsx).
import { test, expect } from '@playwright/test';
import { seedPrefs } from './helpers';

test('POST /share (multipart) -> 303 -> /check?text=... pre-filled', async ({ page, request, baseURL }) => {
  const text = 'Check this out';
  const url = 'https://example.com/scam';

  const res = await request.post(`${baseURL}/share`, {
    multipart: { title: 'A shared message', text, url },
    maxRedirects: 0,
  });
  expect(res.status()).toBe(303);
  const location = res.headers()['location'];
  expect(location).toMatch(/^\/check\?text=/);
  expect(decodeURIComponent(location.split('text=')[1])).toBe(`${text} ${url}`);

  await seedPrefs(page, { lang: 'en' });
  await page.goto(location);
  await expect(page.getByTestId('check-input')).toHaveValue(`${text} ${url}`);
});
