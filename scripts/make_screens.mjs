#!/usr/bin/env node
// Renders realistic phone-screenshot test fixtures (WhatsApp / SMS / Telegram /
// trading-app / UPI-collect / official-notice mockups) to PNG, plus the matching
// tests/fixtures/screens/manifest.yaml, for Satark's screenshot ingestion path
// (on-server OCR + local vision model). All content is fictional.
//
// Run:
//   cd web && node ../scripts/make_screens.mjs
//
// Playwright lives in web/node_modules, not scripts/ or the repo root, so it is
// resolved explicitly via createRequire pointed at web/package.json (works
// regardless of the process cwd).

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(REPO_ROOT, 'tests', 'fixtures', 'screens');
mkdirSync(OUT_DIR, { recursive: true });

const req = createRequire(path.join(REPO_ROOT, 'web', 'package.json'));
const { chromium } = req('playwright');

// ---------------------------------------------------------------------------
// Fonts — embedded as base64 data: URIs so Devanagari renders correctly no
// matter what's registered in the host's fontconfig (this sandbox has zero
// Devanagari-capable fonts installed; reusing the Noto Sans Devanagari files
// already vendored in a sibling project avoids a system font install or a
// network fetch).
// ---------------------------------------------------------------------------
const FONT_DIR = path.join(__dirname, 'fonts');
const b64 = (f) => readFileSync(path.join(FONT_DIR, f)).toString('base64');
const DEVA_400 = b64('NotoSansDevanagari-400.ttf');
const DEVA_700 = b64('NotoSansDevanagari-700.ttf');

const FONT_FACE_CSS = `
@font-face{font-family:'Deva';src:url(data:font/ttf;base64,${DEVA_400}) format('truetype');font-weight:400;font-style:normal;}
@font-face{font-family:'Deva';src:url(data:font/ttf;base64,${DEVA_700}) format('truetype');font-weight:700;font-style:normal;}
`;

const FONT_STACK = "'Deva','Noto Color Emoji',Roboto,'Segoe UI',Ubuntu,Arial,sans-serif";

// ---------------------------------------------------------------------------
// Small shared helpers
// ---------------------------------------------------------------------------
const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const AVATAR_PALETTE = ['#E17076', '#7BC862', '#E5CA77', '#65AADD', '#A695E7', '#EE7AAE', '#4FAE9B'];
function avatar(name, size = 40) {
  const letter = esc((name.match(/[A-Za-z0-9ऀ-ॿ]/) || ['?'])[0].toUpperCase());
  const color = AVATAR_PALETTE[name.length % AVATAR_PALETTE.length];
  return `<div style="width:${size}px;height:${size}px;min-width:${size}px;border-radius:50%;background:${color};
    display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:${size * 0.45}px;">${letter}</div>`;
}

function mkTimes(n, startH, startM) {
  const out = [];
  let h = startH, m = startM;
  for (let i = 0; i < n; i++) {
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = ((h + 11) % 12) + 1;
    out.push(`${h12}:${String(m).padStart(2, '0')} ${ampm}`);
    m += 3;
    if (m >= 60) { m -= 60; h += 1; }
  }
  return out;
}

function statusBar(fg = '#000') {
  return `<div style="height:28px;flex:none;display:flex;align-items:center;justify-content:space-between;
    padding:0 18px;font-size:13px;font-weight:600;color:${fg};font-family:${FONT_STACK};">
    <span>9:41</span><span style="letter-spacing:2px;">📶 🔋</span></div>`;
}

function doc(bodyHtml, extraCss = '') {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
${FONT_FACE_CSS}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased;}
html,body{margin:0;padding:0;width:390px;}
body{font-family:${FONT_STACK};}
.screen{display:flex;flex-direction:column;min-height:844px;width:390px;}
${extraCss}
</style></head><body><div class="screen">${bodyHtml}</div></body></html>`;
}

// ---------------------------------------------------------------------------
// Templates — each takes the screen's `render` data and returns full HTML.
// ---------------------------------------------------------------------------

function tplWhatsAppChat(r) {
  const times = mkTimes(r.bubbles.length, 10, 12);
  const bubbles = r.bubbles.map((b, i) => {
    const mine = b.from === 'me';
    const senderLabel = !mine && r.isGroup && b.sender
      ? `<div style="font-size:12.5px;font-weight:700;color:#d2691e;margin-bottom:2px;">${esc(b.sender)}</div>` : '';
    return `<div style="align-self:${mine ? 'flex-end' : 'flex-start'};max-width:80%;background:${mine ? '#DCF8C6' : '#FFFFFF'};
      border-radius:8px;padding:7px 9px;box-shadow:0 1px 1px rgba(0,0,0,.12);">
      ${senderLabel}
      <div style="font-size:14px;line-height:1.35;color:#111;white-space:pre-wrap;">${esc(b.text)}</div>
      <div style="text-align:right;font-size:11px;color:#8d8d8d;margin-top:3px;">${mine ? '<span style="color:#53bdeb;">✓✓</span> ' : ''}${times[i]}</div>
    </div>`;
  }).join('');
  const body = `
    ${statusBar('#fff')}
    <div style="background:#075E54;flex:none;display:flex;align-items:center;gap:10px;padding:8px 12px;color:#fff;">
      <span style="font-size:20px;">←</span>
      ${avatar(r.contactName, 34)}
      <div style="flex:1;min-width:0;">
        <div style="font-size:15.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(r.contactName)}</div>
        <div style="font-size:12px;opacity:.85;">${esc(r.contactSub)}</div>
      </div>
      <span style="font-size:16px;">📹</span><span style="font-size:16px;">📞</span><span style="font-size:18px;">⋮</span>
    </div>
    <div style="flex:1;background:#E5DDD3;padding:10px;display:flex;flex-direction:column;gap:6px;">${bubbles}</div>
    <div style="flex:none;background:#F0F0F0;border-top:1px solid #ddd;display:flex;align-items:center;gap:8px;padding:8px 10px;">
      <div style="flex:1;background:#fff;border-radius:18px;padding:8px 14px;color:#999;font-size:13.5px;">Message</div>
      <span style="font-size:18px;">🎤</span>
    </div>`;
  return doc(body);
}

function tplSmsThread(r) {
  const times = mkTimes(r.bubbles.length, 11, 2);
  const bubbles = r.bubbles.map((b, i) => {
    const mine = b.from === 'me';
    return `<div style="align-self:${mine ? 'flex-end' : 'flex-start'};max-width:82%;">
      <div style="background:${mine ? '#1A73E8' : '#ECECEC'};color:${mine ? '#fff' : '#111'};
        border-radius:16px;padding:8px 13px;font-size:14px;line-height:1.35;white-space:pre-wrap;">${esc(b.text)}</div>
      <div style="font-size:10.5px;color:#9b9b9b;margin-top:2px;text-align:${mine ? 'right' : 'left'};">${times[i]}</div>
    </div>`;
  }).join('');
  const body = `
    ${statusBar('#000')}
    <div style="background:#fff;flex:none;display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #eee;">
      <span style="font-size:20px;">←</span>
      ${avatar(r.sender, 34)}
      <div style="flex:1;min-width:0;">
        <div style="font-size:15.5px;font-weight:700;letter-spacing:.3px;">${esc(r.sender)}</div>
        <div style="font-size:11.5px;color:#777;">Text Message</div>
      </div>
      <span style="font-size:17px;">📞</span><span style="font-size:17px;">ℹ️</span>
    </div>
    <div style="flex:1;background:#fff;padding:12px 10px;display:flex;flex-direction:column;gap:10px;">${bubbles}</div>
    <div style="flex:none;background:#fff;border-top:1px solid #eee;display:flex;align-items:center;gap:8px;padding:8px 10px;">
      <div style="flex:1;background:#F0F0F0;border-radius:18px;padding:8px 14px;color:#999;font-size:13.5px;">Text message</div>
      <span style="font-size:20px;color:#1A73E8;">➤</span>
    </div>`;
  return doc(body);
}

function tplTelegramPost(r) {
  const paras = r.lines.map(l => `<div style="font-size:14.5px;line-height:1.45;color:#1c1c1c;margin-bottom:8px;white-space:pre-wrap;">${esc(l)}</div>`).join('');
  const body = `
    ${statusBar('#fff')}
    <div style="background:#2AABEE;flex:none;display:flex;align-items:center;gap:10px;padding:8px 12px;color:#fff;">
      <span style="font-size:20px;">←</span>
      ${avatar(r.channelName, 34)}
      <div style="flex:1;min-width:0;">
        <div style="font-size:15.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(r.channelName)}</div>
        <div style="font-size:12px;opacity:.9;">${esc(r.members)}</div>
      </div>
      <span style="font-size:16px;">🔍</span><span style="font-size:18px;">⋮</span>
    </div>
    <div style="flex:1;background:#E7EBF0;padding:12px;">
      <div style="background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 2px rgba(0,0,0,.08);">
        <div style="font-size:12px;font-weight:700;color:#2AABEE;margin-bottom:8px;">📌 PINNED MESSAGE</div>
        ${paras}
        <div style="font-size:11.5px;color:#9aa5b1;margin-top:6px;">👁 ${r.views} &nbsp;·&nbsp; ${r.time}</div>
      </div>
    </div>`;
  return doc(body);
}

function tplTradingApp(r) {
  const bars = Array.from({ length: 10 }, (_, i) => {
    const h = 14 + ((i * 37) % 40);
    return `<div style="width:8px;height:${h}px;background:linear-gradient(#5be37d,#2fae55);border-radius:2px;"></div>`;
  }).join('');
  const body = `
    ${statusBar('#fff')}
    <div style="background:#121826;flex:none;display:flex;align-items:center;justify-content:space-between;padding:12px 16px;color:#fff;">
      <div style="font-size:17px;font-weight:700;">${esc(r.appName)}</div>
      <span style="font-size:18px;">☰</span>
    </div>
    <div style="flex:1;background:#121826;padding:18px 16px;color:#fff;position:relative;">
      <div style="font-size:12.5px;color:#9aa4b2;">${esc(r.profitCaption)}</div>
      <div style="font-size:32px;font-weight:700;margin-top:4px;">${esc(r.portfolioValue)}</div>
      <div style="display:inline-block;background:#1e3a2a;color:#5be37d;font-size:12.5px;font-weight:700;
        border-radius:20px;padding:4px 12px;margin-top:8px;">${esc(r.badge)}</div>
      <div style="display:flex;align-items:flex-end;gap:6px;height:60px;margin-top:26px;">${bars}</div>
      <div style="margin-top:28px;background:#1DB954;color:#fff;text-align:center;border-radius:10px;padding:13px;font-weight:700;font-size:15px;">${esc(r.withdrawLabel)}</div>

      <div style="position:absolute;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:24px;">
        <div style="background:#fff;color:#111;border-radius:14px;padding:22px 20px;width:100%;box-shadow:0 8px 24px rgba(0,0,0,.4);">
          <div style="font-size:30px;text-align:center;margin-bottom:6px;">⚠️</div>
          <div style="font-size:16px;font-weight:700;text-align:center;margin-bottom:8px;">${esc(r.popupTitle)}</div>
          <div style="font-size:13.5px;line-height:1.45;color:#333;text-align:center;">${esc(r.popupBody)}</div>
          <div style="display:flex;gap:10px;margin-top:16px;">
            <div style="flex:1;text-align:center;border:1px solid #ccc;border-radius:8px;padding:10px;font-size:13.5px;color:#555;font-weight:600;">${esc(r.buttons[1])}</div>
            <div style="flex:1;text-align:center;background:#E8453C;color:#fff;border-radius:8px;padding:10px;font-size:13.5px;font-weight:700;">${esc(r.buttons[0])}</div>
          </div>
        </div>
      </div>
    </div>`;
  return doc(body);
}

function tplUpiRequest(r) {
  const body = `
    ${statusBar('#000')}
    <div style="background:#fff;flex:none;display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid #eee;">
      <span style="font-size:20px;">←</span>
      <div style="font-size:16px;font-weight:700;">Collect Request</div>
    </div>
    <div style="flex:1;background:#F7F7FA;padding:28px 22px;display:flex;flex-direction:column;align-items:center;">
      ${avatar(r.payeeName, 56)}
      <div style="font-size:17px;font-weight:700;margin-top:14px;text-align:center;">${esc(r.payeeName)}</div>
      <div style="font-size:13px;color:#777;margin-top:2px;">${esc(r.wantsLabel)}</div>
      <div style="font-size:34px;font-weight:700;margin-top:14px;">${esc(r.amount)}</div>
      <div style="font-family:'Courier New',monospace;font-size:13px;background:#EDEBFA;color:#4b3fa3;
        border-radius:8px;padding:6px 12px;margin-top:12px;">${esc(r.upiId)}</div>
      <div style="font-size:13px;color:#555;background:#fff;border:1px solid #eee;border-radius:10px;
        padding:12px 14px;margin-top:18px;line-height:1.4;width:100%;">${esc(r.note)}</div>
      <div style="display:flex;gap:12px;margin-top:26px;width:100%;">
        <div style="flex:1;text-align:center;border:1.5px solid #888;border-radius:24px;padding:12px;font-weight:700;font-size:14px;color:#444;">${esc(r.buttons[0])}</div>
        <div style="flex:1;text-align:center;background:#5B3FD6;color:#fff;border-radius:24px;padding:12px;font-weight:700;font-size:14px;">${esc(r.buttons[1])}</div>
      </div>
    </div>`;
  return doc(body);
}

function tplOfficialNotice(r) {
  if (r.kind === 'email') {
    const body = `
      ${statusBar('#000')}
      <div style="background:#fff;flex:none;display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid #eee;">
        <span style="font-size:20px;">←</span><div style="font-size:15px;font-weight:700;">Inbox</div>
      </div>
      <div style="flex:1;background:#fff;padding:18px 18px;">
        <div style="font-size:16px;font-weight:700;margin-bottom:10px;">${esc(r.subject)}</div>
        <div style="font-size:12.5px;color:#666;margin-bottom:3px;"><b>From:</b> ${esc(r.from)}</div>
        <div style="font-size:12.5px;color:#666;margin-bottom:12px;"><b>To:</b> ${esc(r.to)}</div>
        <hr style="border:none;border-top:1px solid #eee;margin-bottom:14px;">
        ${r.body.map(p => `<div style="font-size:14px;line-height:1.55;color:#222;margin-bottom:10px;">${esc(p)}</div>`).join('')}
        <div style="display:inline-flex;align-items:center;gap:6px;background:#F3F3F3;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#444;margin-top:6px;">📄 ${esc(r.attachment)}</div>
      </div>`;
    return doc(body);
  }
  const stamp = r.stampText ? `<div style="align-self:flex-end;border:2px dashed #B23B3B;color:#B23B3B;
      transform:rotate(-7deg);padding:7px 14px;font-weight:700;font-size:12.5px;letter-spacing:1px;
      text-transform:uppercase;margin-top:18px;">${esc(r.stampText)}</div>` : '';
  const body = `
    ${statusBar('#000')}
    <div style="flex:1;background:#EFEAE0;padding:22px 16px;">
      <div style="background:#fff;border:1px solid #ddd;border-radius:4px;padding:22px 18px;box-shadow:0 1px 3px rgba(0,0,0,.08);
        display:flex;flex-direction:column;">
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:17px;font-weight:700;text-align:center;">${esc(r.heading)}</div>
        <div style="text-align:center;font-size:11px;letter-spacing:2px;color:#777;margin-top:4px;">NOTICE</div>
        <div style="text-align:center;font-size:11px;color:#999;margin-top:8px;font-family:'Courier New',monospace;">${esc(r.refLine)}</div>
        <hr style="border:none;border-top:1px solid #ddd;margin:14px 0;">
        ${r.body.map(p => `<div style="font-family:Georgia,'Times New Roman',serif;font-size:13.5px;line-height:1.6;color:#222;margin-bottom:10px;">${esc(p)}</div>`).join('')}
        ${stamp}
      </div>
    </div>`;
  return doc(body);
}

// ---------------------------------------------------------------------------
// Screen data — 24 specs. `identifiers` must occur verbatim in the derived
// shown_text (enforced below) so the manifest stays trustworthy.
// ---------------------------------------------------------------------------
const SCREENS = [
  // ---------------- SCAM (16) ----------------
  {
    id: 'sc-01', template: 'trading_app', lang: 'en', expect: 'scam', source_id: 'hv2_001',
    identifiers: ['tradezenith.tax@ybl'],
    render: {
      appName: 'TradeZenith', profitCaption: 'Total Portfolio Value (Profit ready for withdrawal)',
      portfolioValue: '₹1,84,000', badge: '▲ Profit — Ready to withdraw', withdrawLabel: 'Withdraw',
      popupTitle: 'Withdrawal Tax Required',
      popupBody: 'As per new RBI guidelines, a one-time 18% withdrawal tax must be paid to unlock your wallet. Pay ₹33,120 to UPI ID tradezenith.tax@ybl within 2 hours or your account gets frozen immediately.',
      buttons: ['Pay Now', 'Cancel'],
    },
  },
  {
    id: 'sc-02', template: 'upi_request', lang: 'hi', expect: 'scam', source_id: 'hd-09 (+identifier)',
    identifiers: ['policybonus.desk@ybl'],
    render: {
      payeeName: 'Policy Bonus Desk', wantsLabel: 'भुगतान का अनुरोध कर रहा है', amount: '₹1,100',
      upiId: 'policybonus.desk@ybl', note: 'GST चार्ज – पुरानी पॉलिसी का बोनस मैच्योरिटी अमाउंट रिलीज़ करने के लिए ज़रूरी।',
      buttons: ['अस्वीकार करें', 'भुगतान करें'],
    },
  },
  {
    id: 'sc-03', template: 'upi_request', lang: 'hi', expect: 'scam', source_id: 'hv2_012 (+identifier)',
    identifiers: ['greenvalley.invest@ybl'],
    render: {
      payeeName: 'Green Valley Farmland Scheme', wantsLabel: 'भुगतान का अनुरोध कर रहा है', amount: '₹50,000',
      upiId: 'greenvalley.invest@ybl', note: 'मासिक फिक्स्ड रिटर्न स्कीम की पहली किस्त — ₹3,000 प्रति लाख हर महीने गारंटीड।',
      buttons: ['अस्वीकार करें', 'भुगतान करें'],
    },
  },
  {
    id: 'sc-04', template: 'telegram_post', lang: 'en', expect: 'scam', source_id: 'hv2_007',
    identifiers: ['profitking.signals@okaxis'],
    render: {
      channelName: 'Profit King Signals', members: '61,204 members', views: '38.1K', time: '10:32 AM',
      lines: [
        '🎯 PROFIT KING SIGNALS 🎯 Our premium Telegram group has a 92% win rate on Nifty & Banknifty options.',
        'Members made 3x their capital in just 6 weeks.',
        'First 50 users get lifetime access for ₹999 only (actual price ₹15,000). Pay via UPI profitking.signals@okaxis and send screenshot to unlock group link.',
      ],
    },
  },
  {
    id: 'sc-05', template: 'telegram_post', lang: 'hi', expect: 'scam', source_id: 'hv2_009 (+identifier)',
    identifiers: ['dailyprofit.vip@ybl'],
    render: {
      channelName: 'डेली प्रॉफिट सिग्नल्स', members: '18,430 सदस्य', views: '9,870', time: '11:05 AM',
      lines: [
        'शेयर बाज़ार में कमाई का सुनहरा मौका! हमारा प्रीमियम सिग्नल ग्रुप पिछले 6 महीने से 88% सफलता दर के साथ चल रहा है।',
        'रोज़ाना 2 इंट्राडे कॉल, टारगेट और स्टॉपलॉस के साथ। सिर्फ ₹1500 प्रति माह में जॉइन करें और हर महीने ₹50,000+ कमाने वाले सैकड़ों सदस्यों में शामिल हों।',
        'सीटें सीमित हैं, आज ही रजिस्टर करें 🙏 पेमेंट करें: dailyprofit.vip@ybl',
      ],
    },
  },
  {
    id: 'sc-06', template: 'telegram_post', lang: 'en', expect: 'scam', source_id: 'en-07',
    identifiers: ['apnacoin-claim.xyz'],
    render: {
      channelName: 'ApnaCoin Official', members: '104,558 members', views: '52.7K', time: '6:18 PM',
      lines: [
        '🎁 CONGRATULATIONS! Your wallet address is whitelisted for the ApnaCoin airdrop – claim 5000 APN tokens (~₹40,000 value) free.',
        'To claim, connect your wallet and enter your 12-word recovery phrase on apnacoin-claim.xyz within 24 hrs or the allocation will be forfeited.',
      ],
    },
  },
  {
    id: 'sc-07', template: 'whatsapp_chat', lang: 'en', expect: 'scam', source_id: 'hv2_010',
    identifiers: ['+91 98450 11223'],
    render: {
      contactName: 'NovaTech IPO Desk', contactSub: '+91 98450 11223', isGroup: false,
      bubbles: [
        { from: 'them', text: 'Exclusive HNI Quota Alert 📈 We have reserved institutional category allotment for the upcoming NovaTech Industries IPO before listing.' },
        { from: 'them', text: 'Guaranteed allotment + 150% listing gain expected. Minimum investment Rs 2,00,000.' },
        { from: 'them', text: 'Limited slots — contact our RM on +91 98450 11223 to block your quota today.' },
      ],
    },
  },
  {
    id: 'sc-08', template: 'whatsapp_chat', lang: 'hi', expect: 'scam', source_id: 'hv2_011 (+identifier)',
    identifiers: ['+91 97120 55678', 'novaunlisted.ipo@okaxis'],
    render: {
      contactName: 'Suresh – Unlisted Shares', contactSub: '+91 97120 55678', isGroup: false,
      bubbles: [
        { from: 'them', text: 'hlo sir, apka number hamare client ne diya tha.' },
        { from: 'them', text: 'ek unlisted company ka IPO aa raha hai, pre-IPO shares abhi se mil rahe hain HNI quota mein, listing pe 3x guarantee hai.' },
        { from: 'them', text: 'minimum 1 lakh lagana hoga, booking jaldi karo kal rate badh jayega. payment UPI se kar dena: novaunlisted.ipo@okaxis, ya call karo +91 97120 55678 pe' },
      ],
    },
  },
  {
    id: 'sc-09', template: 'whatsapp_chat', lang: 'hi', expect: 'scam', source_id: 'hv2_002',
    identifiers: ['zencoin.tds@okicici'],
    render: {
      contactName: 'Zencoin Traders India 🚀', contactSub: '243 members', isGroup: true,
      bubbles: [
        { from: 'them', sender: 'Rahul', text: 'bhai maine Zencoin Trader app se 2.3 lakh kama liya but withdraw karne pe bol rahe 15% TDS pehle jama karo warna account band ho jayega 😭 kisi ne aisa dekha hai kya, UPI id hai zencoin.tds@okicici' },
        { from: 'me', text: 'bhai ye scam lagta hai, asli broker withdraw pe TDS jaisa kuch nahi maangta. mat bhejna paisa' },
      ],
    },
  },
  {
    id: 'sc-10', template: 'whatsapp_chat', lang: 'hi', expect: 'scam', source_id: 'hv2_021',
    identifiers: ['+91 22 6104 7788'],
    render: {
      contactName: 'Unknown', contactSub: '+91 22 6104 7788', isGroup: false,
      bubbles: [
        { from: 'them', text: 'यह कॉल मुंबई साइबर क्राइम ब्रांच से है। आपके आधार नंबर से जुड़े बैंक अकाउंट का इस्तेमाल एक मनी लॉन्ड्रिंग केस में हुआ है।' },
        { from: 'them', text: 'जब तक जांच पूरी नहीं होती, आप "डिजिटल अरेस्ट" में हैं, घर से बाहर नहीं जा सकते और किसी को इस कॉल के बारे में नहीं बता सकते।' },
        { from: 'them', text: 'वेरिफिकेशन के लिए अपनी सारी बैंक डिटेल्स और एक छोटी सी "क्लीयरेंस फीस" तुरंत जमा करनी होगी, वरना गिरफ्तारी वारंट जारी हो जाएगा।' },
        { from: 'them', text: 'अपना केस नंबर नोट कर लीजिए और सिर्फ इस नंबर +91 22 6104 7788 पर ही दोबारा संपर्क कीजिएगा, किसी और को मत बताइए।' },
        { from: 'me', text: 'क्या ये सच में हो सकता है? पुलिस ऐसे कॉल पर पैसे नहीं मांगती' },
      ],
    },
  },
  {
    id: 'sc-11', template: 'whatsapp_chat', lang: 'hi', expect: 'scam', source_id: 'hd-05 (+identifier)',
    identifiers: ['tokendrop-claim.in'],
    render: {
      contactName: 'Wallet Airdrop Alerts', contactSub: 'broadcast list', isGroup: false,
      bubbles: [
        { from: 'them', text: 'बधाई हो 🎉 आपका वॉलेट एक नए क्रिप्टो प्रोजेक्ट के एयरड्रॉप के लिए चुना गया है।' },
        { from: 'them', text: '₹35,000 के बराबर टोकन क्लेम करने के लिए अपनी 12 words वाली रिकवरी फ्रेज़ नीचे दिए गए ऐप में डालें: tokendrop-claim.in' },
        { from: 'them', text: 'समय सीमा सिर्फ 6 घंटे है।' },
      ],
    },
  },
  {
    id: 'sc-12', template: 'whatsapp_chat', lang: 'en', expect: 'scam', source_id: 'en-11',
    identifiers: [],
    render: {
      contactName: 'Vikram 😊', contactSub: 'online', isGroup: false,
      bubbles: [
        { from: 'them', text: 'Hey 😊 been really enjoying our late night calls this week.' },
        { from: 'them', text: "Btw I mentioned my cousin runs a private trading desk in Singapore — he's letting a few of us close friends in on his USDT arbitrage pool, already turned my ₹80,000 into ₹2.1 lakh in 3 weeks." },
        { from: 'them', text: "I don't want you to miss it, want me to ask him to open a slot for you too? 🥰" },
        { from: 'me', text: 'wait, really?? how would I even join' },
      ],
    },
  },
  {
    id: 'sc-13', template: 'whatsapp_chat', lang: 'hi', expect: 'scam', source_id: 'hd-08',
    identifiers: [],
    render: {
      contactName: 'Arjun 🙂', contactSub: 'online', isGroup: false,
      bubbles: [
        { from: 'them', text: '[वॉइस नोट ट्रांसक्रिप्ट 1:04] अरे यार, तुमसे बात करके बहुत अच्छा लगता है हर रात।' },
        { from: 'them', text: 'सुनो, मेरे एक दोस्त का क्रिप्टो ट्रेडिंग प्लेटफॉर्म है दुबई में, मैंने ₹50,000 डाले थे पिछले हफ्ते, आज ₹1,40,000 दिखा रहा है।' },
        { from: 'them', text: 'तुम्हारे लिए भी स्पॉट रखवा दूं क्या, सिर्फ हमारे बीच की बात रहेगी।' },
        { from: 'me', text: 'सच में?? मुझे भी बताओ कैसे करूं' },
      ],
    },
  },
  {
    id: 'sc-14', template: 'sms_thread', lang: 'en', expect: 'scam', source_id: 'hv2_023',
    identifiers: ['kyc-verify-cdsl.info/update'],
    render: {
      sender: 'VM-CDSLKY',
      bubbles: [
        { from: 'them', text: 'Dear Customer, your Demat account KYC is incomplete and will be suspended within 24 hrs as per SEBI norms.' },
        { from: 'them', text: 'Update immediately: kyc-verify-cdsl.info/update Failure to comply will freeze all holdings.' },
      ],
    },
  },
  {
    id: 'sc-15', template: 'sms_thread', lang: 'en', expect: 'scam', source_id: 'hv2_026',
    identifiers: [],
    render: {
      sender: 'VK-BRKTEC',
      bubbles: [
        { from: 'them', text: "Hi, this is Rohit from your broker's technical support." },
        { from: 'them', text: "We're migrating your trading account to a new server tonight — to avoid any data loss please install AnyDesk from the Play Store and share the 9-digit code so our engineer can complete it from our end." },
      ],
    },
  },
  {
    id: 'sc-16', template: 'official_notice', lang: 'hi', expect: 'scam', source_id: 'hv2_025',
    identifiers: ['sebi-kyc-update.net/login'],
    render: {
      kind: 'notice', heading: 'SEBI – KYC Compliance Notice', refLine: 'Ref: SEBI/KYC-NTC/2026/88341',
      body: [
        'ALERT: aapka trading account KYC expire ho gaya hai, SEBI ke naye rule ke According 24 hours mein update nahi kiya to account band ho jayega.',
        'yaha click karke update karo: sebi-kyc-update.net/login',
      ],
      stampText: 'KYC Freeze Warning',
    },
  },

  // ---------------- GENUINE (8) ----------------
  {
    id: 'sc-17', template: 'sms_thread', lang: 'en', expect: 'legit', source_id: 'new',
    identifiers: ['1800-123-4567'],
    render: {
      sender: 'VM-EXBANK',
      bubbles: [
        { from: 'them', text: 'Dear Customer, your A/c XX4821 is debited with Rs.2,499.00 on 04-Oct-26 at AMAZON. Avl bal Rs.48,210.32. Not you? Call 1800-123-4567. -Example Bank' },
      ],
    },
  },
  {
    id: 'sc-18', template: 'sms_thread', lang: 'hi', expect: 'legit', source_id: 'new',
    identifiers: ['1800-123-4567'],
    render: {
      sender: 'VM-EXBANK',
      bubbles: [
        { from: 'them', text: 'प्रिय ग्राहक, आपके खाते XX4821 से ₹1,200.00 दिनांक 04-Oct-26 को Amazon पर डेबिट हुए। उपलब्ध शेष ₹52,430.00 है। यह आप नहीं थे? कॉल करें 1800-123-4567। – Example Bank' },
      ],
    },
  },
  {
    id: 'sc-19', template: 'official_notice', lang: 'en', expect: 'legit', source_id: 'en-16',
    identifiers: ['contracts@zenithbroking.in', 'ZB10234', '220145698712'],
    render: {
      kind: 'email', from: 'Zenith Broking Ltd <contracts@zenithbroking.in>', to: 'you@example.com',
      subject: 'Contract Note – Client ZB10234 – 04-Oct-2026',
      body: [
        'Trade confirmation for client ID ZB10234. Bought 25 shares of INFY @ ₹1,452.30 on NSE, order no. 220145698712, brokerage ₹20 + taxes as applicable.',
        'Settlement T+1. This is a system-generated confirmation, no action required. For queries contact your RM during market hours.',
      ],
      attachment: 'ContractNote_ZB10234.pdf',
    },
  },
  {
    id: 'sc-20', template: 'sms_thread', lang: 'en', expect: 'legit', source_id: 'hv2_038',
    identifiers: ['88274451'],
    render: {
      sender: 'AM-BLUPMF',
      bubbles: [
        { from: 'them', text: 'Your SIP of Rs 5,000 in Bluepeak Flexi Cap Fund has been successfully processed on 03-Oct-2026. Folio No: 88274451. Current NAV: Rs 71.42. - Bluepeak Mutual Fund' },
      ],
    },
  },
  {
    id: 'sc-21', template: 'sms_thread', lang: 'hi', expect: 'legit', source_id: 'hv2_039',
    identifiers: [],
    render: {
      sender: 'BR-ZENBRK',
      bubbles: [
        { from: 'them', text: 'aapka Zenith Broking account mein ₹12,340 ka fund add ho gaya hai via UPI, available balance ab ₹45,670 hai. koi action nahi chahiye, yeh sirf confirmation hai.' },
      ],
    },
  },
  {
    id: 'sc-22', template: 'telegram_post', lang: 'en', expect: 'legit', source_id: 'en-15',
    identifiers: [],
    render: {
      channelName: 'SEBI Investor Awareness', members: '2,04,310 members', views: '91.4K', time: '9:00 AM',
      lines: [
        'Investor Awareness: SEBI and NSE remind you that no SEBI-registered intermediary will ever guarantee fixed or "assured" returns, ask you to trade through a personal WhatsApp "account manager", or request your trading password/OTP.',
        'Messages promising "100% guaranteed profit" or a "SEBI-approved algo bot" are commonly used by fraudsters.',
        "Verify any intermediary on the SEBI website before investing. If in doubt, don't invest, don't share OTP.",
      ],
    },
  },
  {
    id: 'sc-23', template: 'official_notice', lang: 'hi', expect: 'legit', source_id: 'hv2_041',
    identifiers: [],
    render: {
      kind: 'notice', heading: 'सेबी निवेशक जागरूकता', refLine: 'Ref: SEBI/AWR/2026/11029',
      body: [
        'निवेशक सावधानी: जो लोग आपसे कहें कि "गारंटीड रिटर्न" मिलेगा या "30 दिन में पैसा डबल" होगा, उनसे सावधान रहें।',
        'कोई भी वास्तविक सलाहकार मुनाफे की गारंटी नहीं दे सकता। निवेश से पहले सलाहकार का रजिस्ट्रेशन सेबी की वेबसाइट पर ज़रूर चेक करें। - सेबी निवेशक जागरूकता',
      ],
      stampText: null,
    },
  },
  {
    id: 'sc-24', template: 'sms_thread', lang: 'en', expect: 'legit', source_id: 'hv2_037',
    identifiers: ['482193'],
    render: {
      sender: 'VM-ZENBRK',
      bubbles: [
        { from: 'them', text: 'Dear Customer, OTP for your Zenith Broking login is 482193. Valid for 10 minutes. Do not share this OTP with anyone, including bank officials. - Zenith Broking' },
      ],
    },
  },
];

// ---------------------------------------------------------------------------
// Derive shown_text from the same data that gets rendered (single source of
// truth — avoids the manifest drifting from the pixels), then self-check that
// every declared identifier actually occurs in it.
// ---------------------------------------------------------------------------
function shownTextFor(spec) {
  const r = spec.render;
  switch (spec.template) {
    case 'whatsapp_chat':
      return [`${r.contactName} (${r.contactSub})`, ...r.bubbles.map((b) => b.text)].join('\n');
    case 'sms_thread':
      return [r.sender, ...r.bubbles.map((b) => b.text)].join('\n');
    case 'telegram_post':
      return [`${r.channelName} (${r.members})`, ...r.lines].join('\n');
    case 'trading_app':
      return [`${r.profitCaption}: ${r.portfolioValue}`, r.popupTitle, r.popupBody].join('\n');
    case 'upi_request':
      return [`${r.payeeName} ${r.wantsLabel} ${r.amount}`, `UPI: ${r.upiId}`, r.note].join('\n');
    case 'official_notice':
      return r.kind === 'email'
        ? [`From: ${r.from}`, `To: ${r.to}`, r.subject, ...r.body].join('\n')
        : [r.heading, ...r.body].join('\n');
    default:
      throw new Error(`unknown template ${spec.template}`);
  }
}

function renderHtml(spec) {
  switch (spec.template) {
    case 'whatsapp_chat': return tplWhatsAppChat(spec.render);
    case 'sms_thread': return tplSmsThread(spec.render);
    case 'telegram_post': return tplTelegramPost(spec.render);
    case 'trading_app': return tplTradingApp(spec.render);
    case 'upi_request': return tplUpiRequest(spec.render);
    case 'official_notice': return tplOfficialNotice(spec.render);
    default: throw new Error(`unknown template ${spec.template}`);
  }
}

// ---- validate before spending time rendering anything ----
const ids = new Set();
for (const s of SCREENS) {
  if (ids.has(s.id)) throw new Error(`duplicate id ${s.id}`);
  ids.add(s.id);
  s.shown_text = shownTextFor(s);
  for (const ident of s.identifiers) {
    if (!s.shown_text.includes(ident)) {
      throw new Error(`[${s.id}] identifier ${JSON.stringify(ident)} does not literally occur in shown_text — fix the template data`);
    }
  }
}
if (SCREENS.length !== 24) throw new Error(`expected 24 screens, got ${SCREENS.length}`);
const nScam = SCREENS.filter((s) => s.expect === 'scam').length;
const nLegit = SCREENS.filter((s) => s.expect === 'legit').length;
if (nScam !== 16 || nLegit !== 8) throw new Error(`expected 16 scam / 8 legit, got ${nScam} scam / ${nLegit} legit`);

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------
function yamlStr(s) {
  return '"' + String(s)
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\t/g, '\\t') + '"';
}

async function main() {
  const browser = await chromium.launch();
  const manifestLines = [];
  manifestLines.push('# Auto-generated by scripts/make_screens.mjs — do not hand-edit.');
  manifestLines.push('# Regenerate with: cd web && node ../scripts/make_screens.mjs');
  manifestLines.push('');

  for (const spec of SCREENS) {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
    });
    await page.setContent(renderHtml(spec), { waitUntil: 'load' });
    const file = `${spec.id}.png`;
    await page.screenshot({ path: path.join(OUT_DIR, file), type: 'png', fullPage: true });
    await page.close();

    const idArr = spec.identifiers.length
      ? `[${spec.identifiers.map(yamlStr).join(', ')}]`
      : '[]';
    manifestLines.push(`- id: ${yamlStr(spec.id)}`);
    manifestLines.push(`  file: ${yamlStr(file)}`);
    manifestLines.push(`  template: ${yamlStr(spec.template)}`);
    manifestLines.push(`  lang: ${yamlStr(spec.lang)}`);
    manifestLines.push(`  expect: ${yamlStr(spec.expect)}`);
    manifestLines.push(`  source_id: ${yamlStr(spec.source_id)}`);
    manifestLines.push(`  shown_text: ${yamlStr(spec.shown_text)}`);
    manifestLines.push(`  identifiers: ${idArr}`);
    manifestLines.push('');
    console.log(`rendered ${file}  (${spec.template}, ${spec.lang}, ${spec.expect})`);
  }

  await browser.close();
  writeFileSync(path.join(OUT_DIR, 'manifest.yaml'), manifestLines.join('\n'));

  // Summary, computed from the data (not hand-counted).
  const by = (key) => SCREENS.reduce((acc, s) => ((acc[s[key]] = (acc[s[key]] || 0) + 1), acc), {});
  console.log('\n--- summary ---');
  console.log('by template:', by('template'));
  console.log('by lang:', by('lang'));
  console.log('by expect:', by('expect'));
  console.log(`\nwrote ${SCREENS.length} PNGs + manifest.yaml to ${OUT_DIR}`);
}

main();
