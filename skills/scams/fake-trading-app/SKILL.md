---
name: scams/fake-trading-app
description: Use when a WhatsApp/Telegram "VIP group" or "free course" leads to a trading app outside the Play Store, or when link/app/fee-to-withdraw signals fire (T1).
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C10, C12, C13, C14, C15, C17, SEBI-14, NSE-1, DEP-1]
reason_codes: [URL_SHORTENED, URL_KNOWN_PHISHING, DOMAIN_YOUNG, DOMAIN_LOOKALIKE, BANK_NOT_BANK_IN, SIDELOAD_APK, FREE_HOSTED_LANDING, DOMAIN_UNPOPULAR_FOR_BRAND, APP_NOT_ON_PLAY, APP_DEVELOPER_MISMATCH, APP_CLAIMS_BROKER_NOT_LISTED, FEE_TO_WITHDRAW, URGENCY, VIP_GROUP, UNSOLICITED_CONTACT]
---

## The fake trading-app trap (scam type T1)

How it unfolds: a stranger adds the victim to a WhatsApp or Telegram group. A "professor" and an "assistant" persona post fake profit screenshots, then share a link to install a trading app from outside the Play Store [C10, C12–C14].

**The withdrawal script**, the same in almost every case [C12, C13, C15, C17]:
1. A small withdrawal is allowed early, to build trust.
2. The app's displayed balance then grows quickly — it is just a number on screen, not money with an exchange.
3. A large withdrawal is blocked until "brokerage", a "5% service charge" or "verification charges" are paid.
4. Fake SEBI or STT (securities transaction tax) notices add pressure to pay.
5. The app becomes non-functional once the victim stops paying.

**Machine-checkable flags:** a group invite from a stranger; an app not on the Google Play Store, or a direct `.apk` link; a broker app whose Play listing lacks the "Verified" label (launched March 2026, about 600 apps carry it) [SEBI-14]; an app not on NSE's own list of broker apps [NSE-1]; any wording that ties "withdraw" or "निकासी" to a "tax", "fee" or "unlock" charge.

**What the user should do:**
- Leave the group. Do not engage with "professor" or "assistant" accounts.
- Never pay a fee, tax or charge to release money that is already shown as yours — that single rule catches this entire scam.
- Install a broker's app only from the Play Store, and check for the "Verified" label.
- Trust your depository's consolidated account statement (CAS), not the app's own dashboard, for what you actually hold [DEP-1].
- If money is already gone, stop paying immediately and move to the recovery steps (see `recovery/after-loss`).
