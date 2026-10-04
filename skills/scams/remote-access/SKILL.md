---
name: scams/remote-access
description: Use when a message asks the user to install a remote-access app (AnyDesk, TeamViewer, QuickSupport), share an OTP/password, or offers to "handle" the user's trading account (T8).
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C12, C17, C28, I4C-1]
reason_codes: [REMOTE_ACCESS_REQUEST, OTP_REQUEST, ACCOUNT_HANDLING]
---

## Remote-access apps, OTPs and "account handling" (scam type T8)

How it unfolds: someone offers to trade on the user's behalf, often for a profit share ("50-50 profit"), and asks them to install a remote-access app — AnyDesk, TeamViewer or QuickSupport are the most common — or a malicious APK (Android application package). Debits then happen from the user's own accounts without the user acting, because the attacker can see and control the phone directly [C12, C17, C28].

Sharing an OTP (one-time password) or PIN by message or call achieves the same result without even needing an app: whoever holds the OTP can authorise a payment that looks like it came from the account holder.

**Machine-checkable flags:**
- A request to install AnyDesk, TeamViewer, QuickSupport, RustDesk or any similar screen-sharing app.
- A request to read out or type in an OTP, PIN or password to a third party.
- An offer for someone else to trade the user's account directly ("account handling").

**What the user should do:**
- Never install a remote-access app for someone you do not already know and trust in person.
- Never share an OTP or PIN with anyone — a bank, broker or SEBI (Securities and Exchange Board of India) employee will never ask for one.
- If such an app is already installed, disconnect from the internet, uninstall it, and change your banking passwords immediately.
- Call your bank to block further debits, and report at 1930 or cybercrime.gov.in without delay [I4C-1].
- No one should ever trade your account "for" you in exchange for a profit share — this is not a legitimate service.
