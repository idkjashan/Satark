---
name: education/kyc-and-demat
description: Use when the user asks what KYC or a demat account is, or whether an "institutional account" can skip either.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C.6, C11, DEP-1]
reason_codes: []
fits: [lesson_fake_apps]
---

## KYC and the demat account

**Plain definitions:** KYC (Know Your Customer) means the identity checks a regulated firm must complete before you invest. A demat account is an electronic account at NSDL or CDSL (the two depositories), opened through a depository participant, that actually holds your securities [C.6].

**Everyday analogy:** your demat account is like a bank passbook for shares. The depository's own consolidated account statement (CAS) is the real passbook; a trading app's screen is just a window showing you a copy of it [DEP-1].

**The most common first-timer misunderstanding, in two parts:** first, believing an "institutional account" lets you skip KYC or a demat account — SEBI specifically flags this claim as a fraud pattern [C11]. Second, believing "the balance shown in the app is my real holding" — a fake trading app's numbers never touch a real exchange, so they can show anything at all [C.6].

**Safety tip:** trust your depository's own CAS statement, not any app's dashboard, for what you actually own. If a platform says you don't need KYC or a demat account to invest, that is the scam, not a shortcut.

**Where this connects in Satark:** route the user to the `lesson_fake_apps` lesson, which teaches exactly this CAS-versus-dashboard distinction through the fake trading-app trap.
