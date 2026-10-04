---
name: scams/fake-adviser
description: Use when a message impersonates a registered broker, investment adviser or research analyst (T3) — a name/number mismatch, a lookalike handle, or an off-pattern phone/SMS header.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C12, C20, C21, C22, C23, SEBI-14, TRAI-1, TRAI-2]
reason_codes: [REG_NAME_MISMATCH, ON_CAUTION_LIST, FOREIGN_NUMBER_OFFICIAL_CLAIM, REGULATED_CALL_NOT_1600, PROMO_140_FOR_SERVICE, HEADER_CATEGORY_MISMATCH, MOBILE_SENDER_FOR_BANK, HANDLE_LOOKALIKE_OFFICIAL]
---

## Impersonating a registered broker or adviser (scam type T3)

How it unfolds: a scammer uses a real broker's, investment adviser's (IA) or research analyst's (RA) name and a real-looking registration number, often with a cloned app or website, and promises "assured returns". They ask for login IDs and passwords, and collect fees to personal accounts [C12, C20–C22].

**Rule changes the checker must know:** from 1 May 2026, every registered entity must show its name and registration number on its own social-media profiles — a profile with none, or numbers that do not match SEBI's register, is suspect [C22]. SEBI's press release 60/2025 states SEBI itself emails only from an `@sebi.gov.in` address, and its payments move only through its own `siportal` [SEBI-14].

**Machine-checkable flags:**
- A registration number not on SEBI's list, or whose registered name does not match the sender's claimed name.
- An entity, phone number or handle present on NSE's or BSE's caution list.
- A call claiming to be from a SEBI-regulated entity but made from a foreign number, or a domestic number outside the 1600 series required for service/transactional calls [TRAI-1, TRAI-2].
- A "promotional" 140-series number used for what claims to be a service call.
- An SMS header suffix (-P/-S/-T/-G) that doesn't match a real bank's or broker's pattern.
- A social handle that visually imitates an official broker or regulator account.

**What the user should do:**
- Contact the firm only through the phone number, email or address shown on SEBI's own register — never through numbers given inside the suspicious message.
- Use SEBI Check to verify any UPI ID or bank account before paying.
- Never share a login ID, password or OTP (one-time password) with anyone claiming to be an adviser or broker.
- If the entity is on a caution list, report it rather than contact it.
