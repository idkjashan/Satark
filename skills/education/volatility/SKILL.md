---
name: education/volatility
description: Use when the user asks what volatility is, or why a "cheap" option can still be risky.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C.6, SEBI-13]
reason_codes: []
fits: [sim_s3]
---

## Volatility

**Plain definition:** volatility means how much, and how fast, a price swings [C.6].

**Everyday analogy:** it is like the difference between a calm lake and a stormy sea — the same small boat is far riskier to sail on rough water, even heading to the exact same destination.

**The most common first-timer misunderstanding:** thinking "a small option premium means small risk." It does not. A cheap option can still lose its entire value very quickly if the underlying price swings against it. Options caused 92% of individual F&O (futures and options) traders' losses in FY26 [C.6, SEBI-13].

**Safety tip:** judge risk by how much the price can move and how fast, not by how little money you put in up front — a small initial cost does not cap the speed or completeness of a loss.

**Where this connects in Satark:** offer `sim_s3` (the leverage wipe-out simulator) so the user can see, on a seeded illustrative path, how a swinging market interacts with margin — the same mechanism that makes volatility dangerous under leverage.
