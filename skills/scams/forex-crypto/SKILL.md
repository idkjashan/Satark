---
name: scams/forex-crypto
description: Use when a platform offers leveraged non-INR forex trading or asks for payment into a crypto wallet (T9), or CRYPTO_PAYMENT_REQUEST fires.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C29, RBI-3, RBI-7]
reason_codes: [CRYPTO_PAYMENT_REQUEST]
---

## Unauthorised forex and crypto platforms (scam type T9)

How it unfolds: an ad or message leads to an "account manager" who offers leveraged, non-INR (Indian rupee) currency-pair trading, or a "crypto investment" that asks for deposits into individual bank accounts, personal cards, or directly into a crypto wallet address [C29].

**Why this is almost always unauthorised:** ordinary Indian residents may trade forex only through RBI (Reserve Bank of India)-authorised platforms and authorised dealers, in INR-paired instruments, not leveraged non-INR pairs offered by an offshore "account manager". RBI's Alert List named 95 unauthorised forex platforms after its 19 Nov 2025 update — but that list is not exhaustive, so a platform's absence from it proves nothing [RBI-3].

**Machine-checkable flags:**
- A payment request into a Bitcoin, Ethereum/BNB-chain or TRON (crypto) wallet address for an "investment".
- The platform or domain name matches an entry on the RBI Alert List.
- Leveraged, non-INR currency-pair trading offered to a retail Indian user.

**What the user should do:**
- Use only RBI-authorised platforms, authorised dealers, or recognised exchanges for any currency or crypto activity.
- Treat any request to send money into a personal crypto wallet as a critical warning sign — crypto payments cannot be reversed or traced back the way bank payments can.
- Check the platform's name against RBI's Alert List, and report suspected illegal deposit-taking on RBI's Sachet portal [RBI-7].
- If money has already moved, report immediately (see `recovery/after-loss`); crypto transfers are especially hard to recover, so speed matters even more here.
