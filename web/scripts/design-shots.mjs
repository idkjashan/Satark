// Design-review screenshots against a running Satark API serving web/dist.
// usage: node scripts/design-shots.mjs <baseURL> <outDir> [onlyLang]
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
const [base, out, only] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const SCAM = { en: 'Join our VIP group! SEBI Registered Research Analyst Suresh Mehta (INH000000002). Guaranteed 5% daily profit. Pay registration fee to rajesh.profit@okaxis today only. Download app: https://tradeking-pro.in/app.apk',
  hi: 'रोज़ाना 3% मुनाफ़ा पक्का। VIP ग्रुप में जुड़ें। सीमित सीटें, आज ही जॉइन करें। रजिस्ट्रेशन फ़ीस rajesh.profit@okaxis पर भेजें।' };
const NEWS = { en: 'Beware: a man in Mysuru lost 1.77 crore after being promised guaranteed daily returns on a fake trading app. Police warns investors to stay alert and never share OTP.',
  hi: 'सावधान: ठग रोज़ाना 3% पक्के मुनाफ़े का वादा करके निवेशकों से पैसे ठगते हैं। पुलिस ने जागरूक रहने की सलाह दी।' };
const CHAT = { en: 'What is a SIP?', hi: 'SIP क्या होता है?' };
const slowSSE = () => {
  const orig = EventSource.prototype.addEventListener;
  let chain = 0;
  EventSource.prototype.addEventListener = function (type, fn, o) {
    if (!['open', 'error'].includes(type) && window.__slow) {
      return orig.call(this, type, (e) => { chain += 900; setTimeout(() => fn(e), chain); setTimeout(() => (chain = Math.max(0, chain - 900)), chain + 50); }, o);
    }
    return orig.call(this, type, fn, o);
  };
};
const browser = await chromium.launch();
for (const lang of only ? [only] : ['en', 'hi']) {
  for (const [vn, vp] of [['390', { width: 390, height: 844 }], ['1440', { width: 1440, height: 900 }]]) {
    const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, hasTouch: vn === '390', isMobile: false });
    const page = await ctx.newPage();
    await page.addInitScript((p) => localStorage.setItem('prefs', JSON.stringify(p)), { lang, voice: '', rate: 1, textSize: 'normal', simple: false, theme: 'light', onboarded: true });
    await page.addInitScript(slowSSE);
    const shot = async (n) => { await page.waitForTimeout(450); await page.screenshot({ path: `${out}/${lang}-${vn}-${n}.png` }); };
    const step = async (n, fn) => { try { await fn(); } catch (e) { console.log('FAIL', lang, vn, n, String(e).split('\n')[0]); } };
    await step('home', async () => { await page.goto(base + '/'); await shot('01-home'); });
    await step('check', async () => { await page.goto(base + '/check'); await shot('02-check'); });
    for (const [key, txt] of [['scam', SCAM[lang]], ['news', NEWS[lang]]]) {
      await step(key, async () => {
        await page.goto(base + '/check');
        if (key === 'scam') await page.evaluate(() => (window.__slow = true));
        await page.getByTestId('check-input').fill(txt);
        await page.getByTestId('check-submit').click();
        await page.waitForURL(/\/run\//);
        if (key === 'scam') { await page.waitForTimeout(3600); await shot('03-running'); await page.evaluate(() => (window.__slow = false)); }
        await page.getByTestId('verdict-card').waitFor({ timeout: 25000 });
        await page.waitForTimeout(1500);
        await shot(key === 'scam' ? '04-verdict-scam' : '05-verdict-news');
      });
    }
    await step('chat', async () => {
      await page.route('**/v1/runs/*/events*', async (route) => {
        const r = await route.fetch();
        // the mock LLM never cites lessons; add citations to the first answer so the chip can be shown
        await route.fulfill({ response: r, body: (await r.text()).replace('"cites":[]', '"cites":["lesson:compounding:1","sim:S2"]') });
      });
      await page.goto(base + '/chat/new');
      await shot('06a-chat-empty');
      await page.getByTestId('chat-input').fill(CHAT[lang]);
      await page.getByTestId('chat-send').click();
      await page.getByTestId('chat-answer').first().waitFor({ timeout: 25000 });
      for (const q of ['Is 2% a day possible?', 'How do I spot a fake adviser?', 'What is leverage?']) {
        if (await page.getByTestId('chat-cite').count()) break;
        const n = await page.getByTestId('chat-answer').count();
        await page.getByTestId('chat-input').fill(q);
        await page.getByTestId('chat-send').click();
        await page.waitForFunction((k) => document.querySelectorAll('[data-testid="chat-answer"]').length > k, n, { timeout: 25000 });
      }
      await page.waitForTimeout(600);
      await shot('06-chat-answer');
    });
    await step('learn', async () => { await page.goto(base + '/learn'); await shot('07-learn'); });
    await step('lesson', async () => { await page.goto(base + '/learn/compounding'); await shot('08-lesson'); });
    await step('quiz', async () => {
      for (let i = 0; i < 12; i++) { if (await page.locator('[data-testid^="quiz-option-"]').count()) break; await page.getByTestId('lesson-next').click(); }
      await shot('09a-quiz');
      await page.locator('[data-testid^="quiz-option-"]').first().click();
      await shot('09-quiz-feedback');
    });
    await step('practice', async () => { await page.goto(base + '/practice'); await shot('10-practice'); });
    await step('sim', async () => { await page.goto(base + '/sim/S1'); await page.getByTestId('sim-choice-join').click(); await shot('11-sim'); });
    await step('settings', async () => { await page.goto(base + '/settings'); await shot('12-settings'); });
    await step('onboarding', async () => {
      const c2 = await browser.newContext({ viewport: vp });
      const p2 = await c2.newPage();
      await p2.goto(base + '/');
      await p2.waitForSelector('.lang-cards');
      if (lang === 'hi') await p2.getByTestId('lang-hi').click();
      await p2.waitForTimeout(500);
      await p2.screenshot({ path: `${out}/${lang}-${vn}-00-onboarding.png` });
      await c2.close();
    });
    await ctx.close();
  }
}
await browser.close();
