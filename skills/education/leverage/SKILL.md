---
name: education/leverage
description: Use when the user asks what leverage is, or how F&O margin works, in the offline chat or the learn flow.
languages: [en, hi]
reviewer: pending native/legal review
reviewed_on: 2026-10-03
sources: [C.5, C.6, SEBI-13]
reason_codes: []
fits: [lesson_leverage, sim_s3]
---

## Leverage

**Plain definition:** leverage means controlling a position bigger than your own cash, by posting a smaller amount called margin [C.6].

**Everyday analogy:** it is like a see-saw with you sitting on the far end — a small push on the other side throws you much further than that same push would on level ground.

**The most common first-timer misunderstanding:** thinking "leverage multiplies profits," while forgetting it multiplies losses exactly as fast. At roughly 8–9 times leverage (about what one index-futures lot gives today), a market move of around 12% can wipe out the entire margin [C.5, C.6].

**Safety tip:** SEBI's own study found that 87.7% of individual F&O (futures and options) traders lost money in FY26, totalling ₹91,685 crore, with options responsible for 92% of those losses [SEBI-13]. Leverage is not a shortcut to bigger profits; it is a shortcut to bigger losses, far more often.

**Where this connects in Satark:** route the user to the `lesson_leverage` lesson for the full explanation, and offer `sim_s3` (the leverage wipe-out simulator) so they can see a seeded, illustrative market path play out against real margin numbers.
