---
name: scams/unregistered-education
description: Use when a "trading education" channel gives live trading calls, or uses price data under 30 days old (T6), or LIVE_CALLS fires.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C25, C26, SEBI-9]
reason_codes: [LIVE_CALLS]
---

## Unregistered advice disguised as "education" (scam type T6)

How it unfolds: a paid "course" promises to teach trading, then moves into live "real-time strategies" sessions and paid "mentorship". The loss is two-fold: the course fee itself, and the trading losses that follow live calls given by someone without a research-analyst (RA) or investment-adviser (IA) registration [C25, C26].

**The rule that exposes this:** SEBI's circular of 8 May 2026 allows "education" content to use only price data that is at least 30 days old, effective 1 July 2026. Genuine education explains concepts with old data; it never calls live trades [SEBI-9]. A session using current prices to call live trades is, by definition, unregistered investment advice wearing an "education" label.

**Machine-checkable flags:**
- Live trading calls given during a "course" or "mentorship" session.
- Price data newer than 30 days used in content billed as education.
- Specific buy/sell calls with no research-analyst registration shown.

**What the user should do:**
- Treat any live call inside a paid "education" programme as unregistered advice, not education.
- Check whether the person giving calls is a SEBI-registered IA or RA before following anything they say.
- A real finance course teaches concepts — compounding, risk, diversification — it does not tell you what to buy today.
- If money was lost to course fees followed by trading losses, see `recovery/after-loss` for the reporting steps.

This skill explains the pattern only; it never evaluates or recommends any specific trade (see `policy/no-tips`).
