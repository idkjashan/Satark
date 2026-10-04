---
name: scams/fake-sebi-notice
description: Use when a message looks like an official notice from SEBI, a regulator or government body demanding a "penalty", "STT dues" or compliance payment (T4), or on a digital-arrest threat.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C16, C17, C18, SEBI-4, SEBI-14, RBI-6]
reason_codes: [GOVT_NOT_GOV_IN, OFFICIAL_DOMAIN_SPOOF, DIGITAL_ARREST, FAKE_REGULATOR_NOTICE]
---

## Fake SEBI notices, penalties and digital arrest (scam type T4)

How it unfolds: a forged letterhead or seal, often naming SEBI (Securities and Exchange Board of India), demands "compliance", a "penalty" or STT (securities transaction tax) dues, or escalates into a "digital arrest" — a live video call where someone impersonating police or a court threatens arrest unless money is paid immediately [C16–C18]. SEBI's press release 15/2026 specifically named fake STT notices as an active pattern [SEBI-14].

**Machine-checkable flags:**
- SEBI or government branding combined with a payment demand.
- The sender's domain is not `sebi.gov.in`, or more generally not `.gov.in` for a government claim [SEBI-14].
- A "bank" site that does not end in `.bank.in` — a rule that has applied to Indian banks since 31 Oct 2025 [RBI-6].
- Any threat of arrest, account freeze, or number disconnection made over chat or a call.

**The one fact that ends this scam:** no police force, court or regulator ever arrests a person over a video call, or demands money transferred to "avoid" arrest or to "verify" innocence. This never happens, with no exception.

**What the user should do:**
- Never pay against any notice claiming to be from SEBI, the police, a court or the Income Tax department.
- Verify a SEBI letter on SEBI's own Document Number Verification System (DNVS): it confirms SEBI issued that letter (outward number, date, subject) by sending an OTP to the recipient. It proves the letter was issued, not that its demand is valid [SEBI-4].
- If threatened with arrest, end the call and call 1930 immediately. Do not transfer money, and do not stay on the call "to resolve it".
- Check a suspicious government or bank link against the `.gov.in` / `.bank.in` rule before clicking anything inside it.
