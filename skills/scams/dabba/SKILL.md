---
name: scams/dabba
description: Use when a message offers off-exchange "dabba" or "parallel" trading with no demat account needed (T10), or DABBA fires.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C30, NSE-5]
reason_codes: [DABBA]
---

## Dabba (off-exchange) trading (scam type T10)

How it unfolds: Telegram or WhatsApp channels offer "trading" that never touches a real stock exchange — bets are settled privately between the operator and the customer, based on real market prices, but outside NSE (National Stock Exchange) or BSE systems entirely. NSE's "Caution for Investors" notices have named specific channels, such as "Bull Eye Traders Group" in a notice dated 30 September 2026 [C30, NSE-5]. Margin money is paid directly to the operator, not to any exchange clearing system.

**Machine-checkable flags:**
- The word "dabba" itself, or "parallel trading".
- Claims that "no demat account is needed" to trade.
- An operator settling trades privately rather than through a broker-exchange order flow.

**Why this is always illegal and unprotected:**
- A real exchange trade is cleared through a clearing corporation and reflected in the investor's own demat (electronic securities) account at NSDL or CDSL (the two depositories). Dabba trades are never cleared this way, so there is no Investor Protection Fund, no SEBI grievance route, and nothing to show a regulator if the operator simply disappears with the money.
- Running a dabba operation is a criminal offence for the operator under securities law, not a grey area.

**What the user should do:**
- Trade only through a SEBI (Securities and Exchange Board of India)-registered broker, on a real exchange, with your own demat account.
- Treat "no demat needed" as a certain sign that no real trade is happening.
- Check NSE's and BSE's caution notices for named dabba operators before engaging with any trading group.
- Report a dabba operation to the exchange or on SEBI's Market Intelligence portal.
