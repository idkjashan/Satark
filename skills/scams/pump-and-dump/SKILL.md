---
name: scams/pump-and-dump
description: Use when a tip channel pushes a specific stock with "operator" or "upper circuit" language, or a named entity appears on SEBI's debarred list (T5).
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C26, NSE-3, SEBI-7]
reason_codes: [DEBARRED_ENTITY, PUMP_LANGUAGE]
---

## Pump-and-dump tip channels (scam type T5)

How it unfolds: operators quietly accumulate shares in an illiquid or SME (small and medium enterprise platform) stock. A tip channel then hypes it with "buy" calls and price targets. Retail buying, following the hype, pushes the price up. The operators sell into that demand, and the price collapses once they are out — leaving the followers holding the loss [C26].

Real enforcement examples: the Telegram channel `@bullrun2017` (final SEBI order in 2023, ₹5.68 crore in penalties) and the Hemant Gupta case (May 2026 order, 82 mostly SME stocks, ₹20.25 crore impounded) both followed exactly this pattern [C26].

**Machine-checkable flags:**
- The tipper has no INH (research analyst) registration number.
- Specific price targets are given for a named stock.
- Language such as "operator", "upper circuit", "jackpot call" appears.
- The named person or firm appears on NSE's SEBI-debarred list [NSE-3].

**What the user should do:**
- Never buy or sell based on an unsolicited tip, however confident it sounds.
- Check whether the tipper is a SEBI-registered research analyst before trusting any call.
- Report pump-and-dump tips on SEBI's Market Intelligence portal [SEBI-7].
- Remember: a stock that has already been "hyped" to you has likely already been bought by the people hyping it.

This skill never names, prices or recommends a security — it only explains the pattern (see `policy/no-tips`).
