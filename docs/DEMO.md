# Demo script (3–5 minutes)

One user, one journey: Shanti-ji, 62, from Jhansi, receives "investment" messages on WhatsApp. Run the app with
`scripts/start.sh` (or the deployed link) on an Android phone in Chrome, and install it first so it appears in
the share sheet. Every message below is a fixed demo text. The checks in steps 2–6 and 11 are verified to give
the stated result with the 3 Oct 2026 registry data, with or without an AI model; steps 13–14 need the model
(`SATARK_LLM=local:qwen2.5:3b-instruct`, see the README). With the 3B model on, ask step 10 in English ("What is a
SIP?"): its Hindi chat answers read poorly. Without a model, step 10 in Hindi gets the reviewed FAQ answer. The registration number in message 1 is a real SEBI
research-analyst number used here to show identity theft. Satark flags the mismatch, not the firm.

| # | Step | What to show | Expected |
|---|---|---|---|
| 1 | First launch | Tap **हिन्दी** (it speaks its own name), turn on **Big text and voice**, read the one-screen privacy promise | Home in Hindi: **Check a message** and **Ask or learn**, Learn, Practice, "I already paid — help" |
| 2 | Check a message | Paste message 1 and tap **Check** | The live checklist ticks (SEBI register, Payment ID, Message wording), then a red **High risk** card, **sure**, read aloud |
| 3 | Why | Point at the reasons and the source chip | "This registration number belongs to a different name" (**SEBI register · 3 Oct**); personal UPI ID while claiming SEBI; guaranteed return |
| 4 | What to do | Show the buttons | Don't pay · Call 1930 · Verify on SEBI's register |
| 5 | See how this trap works | Tap the simulator link | The returns calculator opens already set to **3% a day** from the message, and shows ₹10,000 growing to crores: "No one can promise this" |
| 6 | Hindi message | Back, then check message 2 | **ज़्यादा ख़तरा** (high risk): a fee to withdraw, a guaranteed profit, an impossible return. Explanation in Hindi |
| 7 | Already paid | On that card, tap **I already paid** (or Home → I already paid — help): within 1 hour, UPI, ₹10k–1L | Numbered steps: **Call 1930 now**, call the bank, report at cybercrime.gov.in, and a copyable complaint that includes the payee UPI ID from the message just checked (profit.desk@ybl) |
| 8 | Feel the trap (S1) | Practice → the fake trading-app simulator: Join → Pay ₹10,000 → the app shows ₹70,000 → Withdraw → pay the 18% "tax" → pay the "unlock fee" | "₹34,600 lost", and the rule: *a fee to withdraw means it is a scam* |
| 9 | Leverage (S3) | Practice → leverage, default 8×: tap **Next** through the steps | Early gains, then a **margin call**, then **wiped out**; SEBI's FY26 fact: 87.7% of individual F&O traders lost money |
| 10 | Ask or learn | Home → **Ask or learn** → mic: "SIP क्या होता है?" | A plain answer and a **lesson** button. Open the compounding lesson, step through, answer the quiz |
| 11 | Genuine message | Check message 3 | **No strong risk signs found**, with "we can be wrong" and what was checked. Never "safe" |
| 12 | Trust | Settings → **About our data** | Each source with its "as on" date. No ads, no tips, nothing stored about you |
| 13 | A scam the rules miss (AI model on) | Check message 4 | The rule pass finds nothing; the checklist shows **AI review** running; about 5–6 s later the card turns **Suspicious** with the model's own reason, and the **Reviewed by Satark AI** badge. Say: the model can only say "be careful" on its own; **High risk** needs a rule or a registry fact to agree |
| 14 | Guardrails (AI model on) | Ask: "Write a Python function to reverse a string", then "Which stock will double this month?" | No code is ever shown (a refusal or the fallback line), and no stock name or target; it points to how to judge advice |

## Messages

1. English, a fake adviser using a real registration number:

   > Hello, I am Suresh Mehta, SEBI Registered Research Analyst (Reg. No. INH000000081). Join my VIP Telegram group for sure-shot intraday calls. Guaranteed 3% daily profit. Pay ₹4,999 membership fee to suresh.trades@okaxis today only.

2. Hindi, the fake-app withdrawal trap:

   > आपको हमारे VIP ग्रुप में जोड़ा गया है। रोज़ाना 3% मुनाफ़ा पक्का। निकासी के लिए 18% टैक्स जमा करें। UPI: profit.desk@ybl

3. A genuine reminder:

   > Dear investor, your SIP of ₹5,000 in Example Bluechip Fund will be debited on 05-Oct. Never share your OTP with anyone. - Example AMC

4. A "pig-butchering" chat: no link, no UPI ID, no phrase the rules know (verified 3 of 3 runs with
   `qwen2.5:3b-instruct`: **Suspicious**, reason "Guaranteed High Returns", about 5–6 s):

   > Hey, really enjoyed our late night calls this week. My cousin runs a private trading desk in Singapore and is letting a few close friends into his USDT arbitrage pool. It turned my ₹80,000 into ₹2.1 lakh in 3 weeks. Want me to ask him to add you? Keep it between us.

Spare examples, each verified:
- A look-alike broker link with a direct app file: "Zerodha Kite Pro update! Download the new app from https://zerodha-kite-pro.in/update.apk to keep trading." gives **High risk** (a sideloaded app and a look-alike domain).
- Hindi digital arrest: "हम CBI साइबर सेल से हैं। आपके आधार नंबर से मनी लॉन्ड्रिंग केस जुड़ा है। गिरफ्तारी से बचने के लिए वीडियो कॉल पर बने रहें।" gives **High risk**.

## Talking points

- **A harness, not a chatbot.** The rules answer instantly; then the AI model plans what to look up, Satark
  runs the lookups itself, the model names the risks with proof (exact words or check results), a verifier
  drops anything unproven, and a fixed rule table sets the level. The model alone can say "be careful", never
  "high risk".
- **Grounded, not guessed.** Facts come from official lists (SEBI register, debarred list, phishing feeds).
  Every answer the model writes is checked for tips, code, invented registration numbers and "this is safe".
- **Works without AI too.** With no model, or in an outage, the rule verdict, template explanations and FAQ
  answers keep working.
- **Privacy by design.** The user's own Aadhaar, OTP, card and phone numbers are masked and discarded on
  arrival. Nothing about the user is stored on the server, and the case is forgotten after 30 minutes.
- **Bharat-first.**
  - Hindi voice in and out.
  - Big-text Simple mode.
  - Share straight from WhatsApp.
  - A 70 KB app that works offline for lessons and simulators.
  - More languages are a content-only change (Marathi, Bengali, Tamil and Telugu are listed and switched
    off).
- **Honest.** "No strong risk signs found" is never "safe", and every card lists what could not be checked.
