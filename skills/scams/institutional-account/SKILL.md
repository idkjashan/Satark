---
name: scams/institutional-account
description: Use when a message offers a retail user "institutional", FPI, QIB, block-trade, OTC or guaranteed IPO-allotment access (T2), or INSTITUTIONAL_ACCESS fires.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C11, C14, SEBI-14]
reason_codes: [INSTITUTIONAL_ACCESS]
---

## Fake "institutional account" and IPO-allotment offers (scam type T2)

How it unfolds: a message offers discounted shares or a "guaranteed" IPO (initial public offering) allotment through a supposed institutional, FPI (foreign portfolio investor), QIB (qualified institutional buyer), block-trade or OTC (over-the-counter) route — often with the line "no demat account or KYC (Know Your Customer) needed" [C11, C14]. Money moves as a "subscription" or "allotment" fee, paid up front.

SEBI's press release 22/2025 specifically named VIP groups and "institutional account" offers with discounted IPOs as an active fraud pattern [SEBI-14].

**Why it is always fake:** retail investors do not get a separate "institutional" route into IPOs. Every investor — retail or institutional — must complete KYC, and every allotment is run through the exchange's own allotment process, never through a private group or agent offering a "guarantee". There is no such thing as a guaranteed allotment; allotment in an oversubscribed IPO is decided by a computer-run lottery or proportionate basis.

**Machine-checkable flags:**
- "Institutional", "FPI", "QIB", "OTC", "block-trade" or "pre-IPO" access offered to an ordinary retail user.
- The words "guaranteed allotment" paired with an IPO.
- A claim that a demat account or KYC can be skipped.

**What the user should do:**
- Apply for IPOs only through your own bank's or broker's app, never through a third party claiming special access.
- Treat any "guaranteed allotment" claim as a certain sign of fraud — no one can guarantee an IPO allotment.
- Never pay a "subscription" or "allotment" fee to a person or group outside your own broker.
- If approached this way, do not share KYC documents, and consider reporting the group (see `recovery/after-loss` for where to report).
