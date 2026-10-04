// Design-review screenshots (not a correctness test - see the task brief). Walks every main
// screen at mobile (390x844) and desktop (1366x768), in English and Hindi, saving PNGs under
// web/test-results/screens/ (git-ignored) for visual inspection. Runs on the 'mobile' project
// like every other spec; the viewport is overridden per test so the same project also renders
// the desktop (>=960px) layout.
import { test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { seedPrefs, submitCheck } from './helpers';

const MOBILE = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 768 };

const SCAM_EN =
  'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). ' +
  'Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. ' +
  'Download app: https://tradeking-pro.in/app.apk';
const SCAM_HI = 'रोज़ाना 3% मुनाफ़ा पक्का। VIP ग्रुप में जुड़ें। सीमित सीटें, आज ही जॉइन करें।';

// fullPage:true mis-renders a `position: sticky` header in this Chromium build (confirmed by
// comparing against a plain viewport capture - the sticky header is fine, only the stitched
// full-page capture overlaps it with the content below). A tall viewport instead of fullPage
// avoids the artifact and still shows everything below the fold on every screen in this app.
async function shot(page: Page, dir: string, name: string): Promise<void> {
  await page.screenshot({ path: `test-results/screens/${dir}/${name}.png` });
}

for (const lang of ['en', 'hi'] as const) {
  for (const viewportName of ['mobile', 'desktop'] as const) {
    const viewport = viewportName === 'mobile' ? MOBILE : DESKTOP;
    const dir = `${viewportName}-${lang}`;
    const scam = lang === 'hi' ? SCAM_HI : SCAM_EN;

    test(`screens: ${dir}`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize(viewport);
      await seedPrefs(page, { lang });

      await page.goto('/');
      await shot(page, dir, '01-home');

      await page.goto('/check');
      await shot(page, dir, '02-check');

      await submitCheck(page, scam);
      await page.waitForSelector('[data-testid="verdict-card"]', { timeout: 20_000 });
      await page.waitForTimeout(400);
      await shot(page, dir, '03-run-verdict');

      await page.goto('/');
      await shot(page, dir, '04-home-with-history');

      await page.goto('/history');
      await shot(page, dir, '05-history');

      await page.goto('/chat/new');
      await shot(page, dir, '06-chat');

      await page.goto('/learn');
      await shot(page, dir, '07-learn');

      await page.goto('/learn/compounding');
      await shot(page, dir, '08-lesson');

      await page.goto('/practice');
      await shot(page, dir, '09-practice');

      await page.goto('/sim/S2');
      await shot(page, dir, '10-sim-s2');
      await page.evaluate(() => window.scrollBy(0, 700));
      await page.waitForTimeout(150);
      await shot(page, dir, '10b-sim-s2-scrolled');

      await page.goto('/sim/S3');
      await shot(page, dir, '11-sim-s3');
      // Language-agnostic: the one primary button on the pre-start screen, whatever ui.start says.
      await page.locator('main button.btn-primary.btn-huge').click();
      await shot(page, dir, '11b-sim-s3-started');

      await page.goto('/help-paid');
      await shot(page, dir, '12-help-paid');

      await page.goto('/settings');
      await shot(page, dir, '13-settings');

      await page.goto('/about-data');
      await shot(page, dir, '14-about-data');
    });
  }
}

test('screens: onboarding (mobile, fresh install)', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await page.goto('/');
  // Onboarding is lazy-loaded (app.tsx `lazy(() => import(...))`) and this is the one screenshot
  // with no earlier navigation in the test to have already warmed that chunk - wait for its own
  // content rather than racing the dynamic import.
  await page.waitForSelector('.lang-cards', { timeout: 10_000 });
  await shot(page, 'mobile-en', '00-onboarding');
});

test('screens: home dark theme (mobile)', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await page.emulateMedia({ colorScheme: 'dark' });
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/');
  await shot(page, 'mobile-en', '00-home-dark');
});

test('screens: home dark theme (desktop)', async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.emulateMedia({ colorScheme: 'dark' });
  await seedPrefs(page, { lang: 'en' });
  await page.goto('/');
  await shot(page, 'desktop-en', '00-home-dark');
});

test('screens: verdict feedback row (mobile, scrolled)', async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await seedPrefs(page, { lang: 'en' });
  await submitCheck(page, SCAM_EN);
  await page.waitForSelector('[data-testid="verdict-card"]', { timeout: 20_000 });
  await page.waitForTimeout(300);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(150);
  await shot(page, 'mobile-en', '03c-run-feedback-row');
});
