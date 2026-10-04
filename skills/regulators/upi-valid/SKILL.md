---
name: regulators/upi-valid
description: Use for any question about @valid UPI IDs, the green thumbs-up icon, SEBI Check, or payment-handle mismatches — and when UPI_*/QR_* signals fire.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [SEBI-2, SEBI-3]
reason_codes: [UPI_PERSONAL_WHILE_CLAIMING_SEBI, UPI_VALID_CATEGORY_MISMATCH, UPI_HANDLE_UNKNOWN, QR_P2P_FOR_BUSINESS, QR_PAYEE_NAME_MISMATCH, QR_MCC_NOT_SECURITIES, QR_UNSIGNED]
---

## @valid UPI IDs and SEBI Check

Since **1 October 2025**, every SEBI (Securities and Exchange Board of India)-registered intermediary collects investor payments only through a standardised UPI (Unified Payments Interface) ID in the form `username.category@validbank` — for example `abc.brk@validhdfc` for a broker, or `xyz.mf@validhdfc` for a mutual fund [SEBI-2]. Category suffixes include `brk` (broker), `bti`, `dp`, `ra`, `ia`, `invit`, `mf`, `pms`, `sreit` and `reit` [SEBI-2].

**What a genuine payment looks like:** the confirmation screen and the QR code both show a white thumbs-up icon inside a green triangle. Its absence is itself a warning sign for a payment claiming to be to a SEBI-registered entity [SEBI-2]. Capital-market UPI payments through this mechanism are capped at about ₹5 lakh a day [SEBI-2]. Intermediaries had to stop accepting payments on their old, non-@valid UPI IDs within roughly 105–180 days of the 11 June 2025 circular.

SEBI Check (`siportal.sebi.gov.in/intermediary/sebi-check`) additionally lets an investor verify a UPI ID — by typing it or scanning its QR code — or a bank account plus IFSC (Indian Financial System Code), to confirm it belongs to a registered intermediary [SEBI-3].

**Machine-checkable flags:**
- A message claims SEBI registration but asks for payment to an ordinary personal UPI ID, not an `@valid` one.
- The category suffix (e.g. `.ia`) does not match what the sender claims to be (e.g. a "broker").
- A UPI ID whose bank suffix is not a recognised bank.
- A QR code that is a personal (P2P) code, has no merchant category code for securities, is unsigned, or whose payee name does not match the claimed entity.

**What the user should do:**
- Never pay a personal UPI ID when someone claims to be a SEBI-registered intermediary.
- Look for the green triangle with the thumbs-up, and check the category suffix matches what they claim to be.
- When unsure, verify the UPI ID or bank account on SEBI Check before paying anything.
