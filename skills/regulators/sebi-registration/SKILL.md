---
name: regulators/sebi-registration
description: Use for any question about what a SEBI registration number is, what it does and does not mean, or how to check one — and when REG_* registry signals fire.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [SEBI-1, C3, C24, C39]
reason_codes: [REG_FORMAT_INVALID, REG_NOT_FOUND, REG_EXPIRED, REG_CATEGORY_MISMATCH, REG_CLAIM_NOT_FOUND, REG_CLAIM_NO_NUMBER]
---

## What a SEBI registration means, and how to check one

SEBI (Securities and Exchange Board of India) registers several kinds of market intermediaries. Each category has its own number format, observed in SEBI's own register exports as of 3 Oct 2026 [C3]:

| Intermediary | Format | Example |
|---|---|---|
| Investment Adviser (IA) | `INA` + 9 digits | INA000012345 |
| Research Analyst (RA) | `INH` + 9 digits | INH000012345 |
| Stock broker | `IN` + one of B/E/F/Z + 9 digits | INZ000012345 |
| Depository participant (DP) | `IN-DP-...` | IN-DP-192-2016 |
| Portfolio manager (PMS) | `INP` + 9 digits | INP000012345 |
| Mutual fund (MF) | `MF/NNN/YY/N` | MF/020/94/8 |

As of 3 Oct 2026, SEBI's registers hold about 1,050 IAs, 2,271 RAs, ~2,737 unique equity-broker numbers, 752+354 DPs, 537 PMS entities and 2,037 AIFs (alternative investment funds) [SEBI-1].

**A correctly formatted number proves nothing by itself.** Anyone can type nine digits after "INA". The only real check is an exact lookup in SEBI's own downloaded register — which is exactly what Satark's registry checkers do.

**What registration does NOT mean:** SEBI's advertisement code bars even registered IAs and RAs from promising or guaranteeing any return, ever [C24, C39]. A registration number next to a "guaranteed 5% daily" claim is not a safer scam — a real registration never justifies a promised return.

**What the user should do:**
- Search the name or number yourself on SEBI's register of intermediaries, never trusting a number as typed in a message.
- If a message claims "SEBI registered" with no number at all, treat that as a warning sign, not a credential.
- Remember that a registration number can be real while the person using it is not who they claim to be — always cross-check the *name*, not just the number.
