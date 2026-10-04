# Satark — Data Sources, APIs and Open-Source Toolkit

| | |
|---|---|
| Document | Research catalogue v1.0, companion to the [HLD](../hld/Satark-HLD.pdf) and the [LLD](../lld/Satark-LLD.md). The LLD cites rows here by id, e.g. `[SEBI-1]`, `[A13]` |
| Date | 3 October 2026. Every fact was checked on this date unless it is marked [S] or UNVERIFIED |
| Scope | Every government service, regulator list, public API, dataset and open-source component found that can help Satark check a scam before money moves (Track A) and teach in the user's language (Track C) |

## TL;DR

**No ready-made open-source harness does this job**, so Satark keeps its own pipeline on PydanticAI and adds proven parts: pydantic-ai-harness guardrails, promptfoo for red-teaming, Phishing.Database and Hagezi blocklists, and the JaanchLo and Ridham115 datasets for evaluation (§1). **The strongest verification data is official and free but rarely an API**: SEBI's registers export to Excel, while NSE, BSE, RBI and AMFI publish lists that must be saved by hand, and SEBI Check, DNVS, the cybercrime "Check Suspect" search and the GST and MCA searches sit behind CAPTCHAs, so Satark deep-links to them (§2). **Permissions are the main risk**: SEBI, NSE, RBI and AMFI terms all limit reuse or automated collection, so send the emails in §5 today.

**Integrate first:**

1. SEBI intermediary registers + the `@valid` UPI-handle rule [SEBI-1, SEBI-2]
2. Caution lists: NSE and BSE notices, RBI Alert List, IRDAI and FIU-IND notices [NSE-5, BSE-1, RBI-3, IRDAI-4, FIU-2]
3. NSE broker-app list + Google Play's "SEBI verified" label [NSE-1, C2]
4. Phishing.Database + Hagezi threat feeds, held locally [A1, A2]
5. RDAP domain age, DNS over HTTPS, and look-alike baselines from CrUX India, Tranco, Wikidata and the `.bank.in` rule [A24, A13, A17, A16, B1, RBI-6]
6. AMFI's list of fund-house apps, handles and WhatsApp links [AMFI-2]
7. Phone and SMS rules: libphonenumber + TRAI's 1600/140 series and header suffixes [D1, TRAI-1, TRAI-2]
8. NSE's SEBI-debarred list + SEBI's enforcement RSS feed [NSE-3, SEBI-5]
9. AMFI distributor (ARN) lookup and RBI's NBFC and digital-lending-app lists [AMFI-1, RBI-1, RBI-2]
10. Razorpay's IFSC dataset + a hand-curated UPI handle map [G1, NPCI-1]

## How to read this catalogue

| Mark | Meaning |
|---|---|
| **USE NOW** | Fits the hackathon sprint |
| **LATER** | Useful, but needs permission, approval, money or heavy work |
| **NOT USEFUL** | Checked and rejected; the reason is given |
| (no mark) | Fetched or tested directly on 3 Oct 2026 |
| [S] | From news or a search snippet only |
| UNVERIFIED | Could not be confirmed; the reason is given |
| `*` after USE NOW | NSE data: NSE's terms prohibit "any systematic or automated data collection activities (including scraping…)" and storing or redistributing data without written permission. Use a snapshot saved by hand, and get permission before production |

**Access types:** API (a program can call it) · BULK (a file downloaded on a schedule and cached) · FORM (a web form, often with a CAPTCHA, a human-verification puzzle) · DEEP LINK (Satark opens the official page with the identifier copied) · APP (only inside an official app).

**Rule for gated services.** Satark never scrapes past a CAPTCHA or an approval gate. It shows a deep link and tells the user what to paste. When an official API appears, the deep link is swapped for a call.

**Network note.** Research ran from outside India. MCA, IEPF, FIU-IND, I4C, NPCI, the IRDAI agency portal and the production data.gov.in host blocked or timed out; they may work from India, so retest from an Indian network.

**Privacy rule used throughout.** Prefer local lists, so nothing the user sends leaves the server. For live APIs, send only a public identifier (a domain, package id or hash prefix), never phone numbers or names typed by the user.

---

## 1. Is there a ready-to-use open-source AI harness?

**No.** No maintained project takes a forwarded message, screenshot, link, UPI ID, number or app, extracts entities, checks Indian registers, scores with rules, explains in Hindi with voice, offers a scam simulation and never gives a stock tip. The closest are fact-checking tiplines (Meedan Check, built for newsrooms) and small 2025–26 hackathon projects; two of those publish reusable CC-BY-4.0 data. The HLD's choice stands: our own bounded pipeline on PydanticAI (MIT), with the parts in §1.3.

### 1.1 Agent frameworks compared (for a multi-user public backend)

| Candidate · language · licence | Multi-user backend | MCP | Agent Skills | Guardrails / typed output | Any model | Maturity | Fit |
|---|---|---|---|---|---|---|---|
| **Goose** · Rust + Electron · Apache-2.0 | No: single-owner local agent; `goose serve` uses one shared secret | Client (extensions are MCP servers) | Native | Permission modes only | Yes (40+ providers) | 54.9k★; v1.53.0 (2 Oct 2026); ~weekly releases | ✗ don't fork |
| **Claude Agent SDK** · Py/TS · MIT repo, Anthropic Commercial Terms | Heavy: one CLI subprocess per session (~1 GiB RAM); isolation is manual | Client | Native, filesystem only | Hooks, permissions | Claude only | v0.2.163 | ✗ for the public path |
| **OpenAI Agents SDK** · Py/TS · MIT | Yes: in-process library; 10 session backends | Client | Sandbox agents only | Input, output and tool guardrails; typed output | Via LiteLLM / any-llm, with caveats | 29.8k★; v0.23.1 | ✓ strong |
| **PydanticAI** · Python · MIT | Yes (library); AG-UI and Vercel AI stream adapters | Client and server | Native via `pydantic-ai-harness[skills]` (never runs scripts) | Typed output, tool approval, `UsageLimits`, hooks | Yes | 20.4k★; v2.54.0 (3 Oct 2026) | ✓ **best Python fit — chosen** |
| **LangGraph** · Python · MIT | Yes (library) or LangSmith Agent Server | Client; Agent Server exposes `/mcp` | Via Deep Agents | Middleware (PII redaction, approval) | Yes | 42.7k★ | ◐ heavier than needed |
| **Google ADK** · Py/TS/Go/Kotlin · Apache-2.0 | Yes; sessions by user and session id | Client; agent as MCP server | `SkillToolset` (experimental) | Callbacks, plugins | Yes ("optimized for Gemini") | 21.7k★; v2.11.0 | ✓ if Gemini-only |
| **Agno** · Python · Apache-2.0 | Yes: AgentOS FastAPI runtime (JWT RBAC claimed, untested) | Client and `/mcp` server | Native | PII and prompt-injection guardrails | Yes | 42.5k★; v3.1.1 | ✓ batteries included |
| **Mastra** · TypeScript · Apache-2.0 except `ee/` | Yes | Client and server | Native | Processors for injection, PII, moderation | Yes | 28.5k★ | ✓ best TypeScript fit |
| **Open WebUI** · Open WebUI licence (branding clause above 50 users) | Multi-user chat app | Client | Native | Filters, pipes | Yes | 154k★ | ✗ as a backend |
| **LibreChat** · MIT (ClickHouse since Nov 2025) | Multi-user chat app | Client | Native | Not checked | Yes | 45.2k★ | ◐ admin or demo UI only |
| **Letta** · Apache-2.0 | In flux (V1 API server retired) | UNVERIFIED | Native (Letta Code) | Not checked | Yes | Last release May 2026 | ✗ |

**Why not fork Goose** (moved to `aaif-goose/goose` under the Linux Foundation's Agentic AI Foundation, Apache-2.0):

- **No tenant model.** One shared secret (`X-Secret-Key`) authenticates every client; sessions live in one local SQLite file tied to working directories; per-user identity, quotas and storage would all be ours to build.
- **Unsafe defaults for hostile input.** The Developer extension (shell, file write and edit) is on by default, and Autonomous mode "can run system commands with your user privileges". A prompt injection inside a scam message becomes shell access on our server.
- **Weight and churn.** A "~27k-token system+tools prefix" re-processed per turn (issue #12501), system-prompt rewrites that break prompt caching (issue #11839), a server protocol replaced in 2026 (REST → ACP), and four releases between 8 Sep and 2 Oct 2026.

Goose stays useful as a developer tool: it reads the same Agent Skills folders, so Satark's skills and MCP server can be tested from it.

### 1.2 Agent Skills format

A skill is a folder with `SKILL.md`: YAML frontmatter (at least `name`, `description`) and a Markdown body, plus optional `scripts/`, `references/`, `assets/`. Progressive disclosure: only names and descriptions sit in the prompt; a tool loads the body when needed. The loading tool per framework: PydanticAI `load_capability`; ADK `load_skill`; Agno `get_skill_instructions`; Open WebUI `view_skill`; Claude Agent SDK `Skill`. PydanticAI's loader "does not enumerate, read, or execute" bundled scripts, the safest fit for Markdown-only knowledge.

### 1.3 Open-source components

| Id | Component | Licence · activity | What it gives Satark | Verdict |
|---|---|---|---|---|
| OSS-1 | **pydantic-ai-harness** | MIT · 0.54.0, 3 Oct 2026 (0.x: API may change) | Input, output and tool guardrails (allow, block, replace, retry, approve); detectors for secrets, emails, cards, IBANs, US SSNs — **no Indian IDs**, but the factories accept extra regexes; prompt-injection defender for tool results; Skills; tool-output limits | **USE NOW** |
| OSS-2 | **promptfoo** | MIT · 0.123.1 | One YAML runs the 60-message regression set; red-team plugins `financial:impartiality` (flags buy/sell/hold calls, price targets, broker picks), `policy`, `hijacking`, `pii`, `indirect-prompt-injection`; Hindi via `language`; GitHub Action. Set `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` to keep generation local | **USE NOW** |
| OSS-3 | **dnstwist** | Apache-2.0 · 20250130 | Look-alike domain permutations (homoglyph, hyphenation, bitsquatting) for proactive hunting | USE NOW (optional; the LLD computes similarity at query time) |
| OSS-4 | **SEBI-webscraper** | MIT · Apr 2026 | Downloads every list on SEBI's recognised-intermediaries page (37 categories, 35,000+ entities, `.xls`); httpx only | **USE NOW** as a starting script (not run against today's site: UNVERIFIED) |
| OSS-5 | **Presidio** | MIT · 2.2.364 | Recognizers IN_AADHAAR, IN_PAN, IN_PASSPORT, IN_VEHICLE_REGISTRATION, IN_VOTER, IN_GSTIN — disabled by default, English only; no UPI recognizer | **USE NOW**: copy the regexes into our detectors |
| OSS-6 | **JaanchLo dataset** | Data CC-BY-4.0 (code AGPL-3.0) | 3,172 rows + 252-row golden holdout, English/Hindi/Hinglish, 8 Indian scam families including investment and deepfake reels; template-built | **USE NOW** for evaluation (do not copy the AGPL code) |
| OSS-7 | Glific (Tech4Dev) | AGPL-3.0 · v8.13.3 | WhatsApp via the Gupshup BSP (Business Solution Provider), Exotel missed-call opt-in, Bhashini speech | LATER: the India/NGO WhatsApp + missed-call phase |
| OSS-8 | Pipecat | BSD-2 · v1.12.0 | Voice bots with Exotel/Plivo/Twilio telephony and Sarvam STT/TTS | LATER: default for IVR |
| OSS-9 | Bolna | MIT · near-daily releases | India-native telephony (Exotel, Vobiz, Plivo, SIP) with Sarvam | LATER |
| OSS-10 | LiveKit Agents | Apache-2.0 · 1.8.4 | WebRTC + SIP voice with Sarvam plugins | LATER |
| OSS-11 | Dograh | BSD-2 · v1.48.0 | Self-hosted voice-agent builder (Pipecat fork) | LATER |
| OSS-12 | MobSF | GPL-3.0 · v4.5.3 | APK static analysis in one Docker container, REST API | LATER |
| OSS-13 | Quark-Engine | GPL-3.0 · v26.9.1 | Rule-based Android malware scoring; lighter than MobSF | LATER |
| OSS-14 | Phishpedia / PhishIntention | CC0-1.0 | Logo-based detection of cloned portals (add Indian broker logos) | LATER |
| OSS-15 | Feluda (Tattle) / Alegre (Meedan) | GPL-3.0 / MIT | Similarity search to reuse verdicts for repeat forwards (images, audio, text) | LATER, when repeat volume justifies it |
| OSS-16 | Llama Guard 4 (12B) | Llama 4 Community Licence, gated | Category S6 "Specialized Advice" covers financial advice: a ready stock-tip classifier; Hindi supported | LATER; test for false positives on our own warnings |
| OSS-17 | pydantic-evals | MIT · 2.54.0 | Typed eval cases with LLM judges, in-process | USE NOW instead of promptfoo for the eval set if the team prefers Python (pick one) |
| OSS-18 | garak | Apache-2.0 · v0.17.0 | Model vulnerability scans | LATER, nightly |
| OSS-19 | Typebot / Chatwoot / n8n | FSL / MIT (+ee) / Sustainable Use | Scripted WhatsApp flows / human inbox for escalations / no-code channel glue | LATER |
| OSS-20 | androguard | Apache-2.0 · v4.1.4 | Reads package name, permissions and signing-certificate digest from an APK | LATER (same as [C4]) |

**Avoid:** Flowise (archived 13 Aug 2026), LLM Guard (archived), Guardrails AI (hub and hosted inference shut down 25 Aug 2026; still moving), Dify (licence bars multi-tenant service; duplicates the pipeline), Rasa Open Source (maintenance mode), TEN Framework (licence terms), Vocode (stale), finstack-mcp (its agents give BUY/HOLD/SELL calls, which breaks the no-tips rule).

**Competitor to know:** `github.com/Pranesh-2323/SCAM-CHECK` (created 3 Oct 2026, no licence) describes itself as "SANGYAN, Track A": 9 regex rules, optional Claude explanation, PII masking, Tesseract OCR, voice, English/Tamil/Hindi, "no stock tips". Satark's difference: live registry, payment-handle and app-label checks plus Track C simulators.

**Simplest WhatsApp path when it is time:** connect Meta's Cloud API webhook straight to FastAPI (one GET for verification, one POST handler); add Glific, Chatwoot or Typebot only for flows, a human inbox or contact management.

---

## 2. Government and regulator sources

### 2.1 SEBI (Securities and Exchange Board of India)

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| SEBI-1 | Recognised intermediaries: [summary](https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes), per category `…OtherAction.do?doRecognisedFpi=yes&intmId=<id>` | Name, registration number, validity, (brokers) exchange and trade name; also contact person, address, phone, email (dropped by Satark). Category ids: IA 13, RA 14, brokers 30/31/32/2, DP 18/19, PMS 33, MF 23, AIF 16, merchant bankers 9, RTAs 10. Counts on 2–3 Oct 2026: IA 1,050; RA 2,271; equity brokers 4,993 rows (2,737 unique numbers); DP 752 + 354; PMS 537; MF 61; AIF 2,037 | BULK: `POST …/IntmExportAction.do?intmId=<id>` returns BIFF8 `.xls` ("Research Analyst as on Oct 03, 2026") only after loading the summary page (cookie) and sending `Referer`; a bare request gets HTTP 530 from the firewall. Reuse "free of charge after taking proper permission by sending a mail" [SEBI-11] | `sebi.reg.*` checkers | **USE NOW** |
| SEBI-2 | [Circular of 11 Jun 2025](https://www.sebi.gov.in/legal/circulars/jun-2025/adoption-of-standardised-validated-and-exclusive-upi-ids-for-payment-collection-by-sebi-registered-intermediaries-from-investors_94535.html) on `@valid` UPI handles | Format `<username>.<category>@valid<bank>`; categories brk, bti, dp, ra, ia, invit, mf, pms, sreit, reit; merchant category code 6211 only; ₹5 lakh/day; thumbs-up-in-green-triangle icon on the payment screen and QR; live 1 Oct 2025; old IDs retired after 180 days | Rule (no API) | `upi.valid_handle` | **USE NOW** |
| SEBI-3 | [SEBI Check](https://siportal.sebi.gov.in/intermediary/sebi-check) (also in the Saa₹thi app) | Verifies a UPI ID (typed or QR photo) or a bank account + IFSC belongs to a registered intermediary; 12 languages | FORM with a conditional CAPTCHA; no public API | Deep link with the identifier copied | **USE NOW** (link) |
| SEBI-4 | [DNVS](https://www.sebi.gov.in/sebiweb/dnvs-authentication-v2.html) (Document Number Verification System) | Confirms SEBI issued a letter (outward number, official, date, subject); OTP to the recipient; proves issuance, not content | FORM | Fake "SEBI notice" screenshots | **USE NOW** (link) |
| SEBI-5 | [Enforcement orders](https://www.sebi.gov.in/enforcement/orders.html) and the [RSS feed](https://www.sebi.gov.in/sebirss.xml) | Interim and final orders (e.g. against unregistered advisers and Telegram channels) | Free XML, live | Names table for `sebi.orders` | USE NOW (ingest) / LATER (checker) |
| SEBI-6 | [SCORES](https://scores.sebi.gov.in) and [SMART ODR](https://smartodr.in) | Complaints and online dispute resolution, **only** against registered entities, listed companies and market institutions; 21-day action report | Login | Recovery path when the entity is registered; otherwise 1930 | **USE NOW** (links) |
| SEBI-7 | [Market Intelligence portal](https://mi.sebi.gov.in/) | Tip-offs (pump-and-dump, unregistered advice) | Login | Report action | **USE NOW** (link) |
| SEBI-8 | [Investor-support index](https://investor.sebi.gov.in/Investor-support.html) | SEBI's own links to exchange broker-app and handle lists, IA/RA web links, online bond platforms, the AMFI app list | HTML | Hub for app and handle checks | **USE NOW** |
| SEBI-9 | [Circular of 8 May 2026](https://www.sebi.gov.in/legal/circulars/may-2026/norms-for-sharing-and-usage-of-price-data-for-educational-purposes_101293.html) on price data for education | One 30-day lag for using price data in education, effective 1 Jul 2026 | Rule | Simulators use fictional or ≥30-day-old data only | **USE NOW** (rule) |
| SEBI-10 | [Investor Charter](https://investor.sebi.gov.in/Investor-charter.html); Saa₹thi app (v2.0, 12 languages [S]) | Rights, dos and don'ts; education | HTML / app | Track C links | USE NOW (links) |
| SEBI-11 | [Website policy](https://www.sebi.gov.in/website-policy.html) | Reproduction allowed after permission by email, source acknowledged; deep links need no permission | — | Constraint: email SEBI | — |
| SEBI-12 | [PaRRVA](https://careparrva.com/) (Past Risk and Return Verification Agency) | CARE verifies return claims of IAs, RAs and algo providers; pilot since Dec 2025 [S] | No public search found (UNVERIFIED) | "Show your PaRRVA link" when returns are claimed | LATER |
| SEBI-13 | F&O studies: [Jan 2023](https://www.sebi.gov.in/sebi_data/attachdocs/jan-2023/1674645296493.pdf), [Sep 2024](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2024/1727085659479.pdf), [Jul 2025](https://www.sebi.gov.in/sebi_data/attachdocs/jul-2025/1751900271726.pdf), [Aug 2026](https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1787233506209.pdf) | FY26: 87.7% of individual F&O traders lost money, ₹91,685 crore in total; options caused 92% of losses; about two-thirds of traders live outside the top 30 cities | PDF | Simulator S3 facts; lessons | **USE NOW** |
| SEBI-14 | Press releases on fraud patterns: [PR 22/2025](https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1744374585901.pdf) (VIP and "institutional" groups, discounted IPOs), [PR 60/2025](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1757068192555.pdf) (SEBI email only from `@sebi.gov.in`, payments only via siportal), [PR 15/2026](https://www.sebi.gov.in/sebi_data/attachdocs/feb-2026/1772114137013.pdf) (fake STT notices), [PR 20/2026](https://www.sebi.gov.in/sebi_data/attachdocs/mar-2026/1774448914437.pdf) (Play "Verified" label; CVV advice), PR 48/2026 (live-trading sessions likely unregistered advice [S]) | Phrases and rules | PDF | Lexicons, `doc.notice`, `link.domain_rules` | **USE NOW** |

### 2.2 Exchanges (NSE, BSE)

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| NSE-1 | [Brokers' mobile apps](https://www.nseindia.com/trade/members-compliance/list-of-mobile-applications) (JSON `/api/list-of-mobile-applications`) | 619 apps from 465 members; 552 unique Play package ids; App Store links; developer | JSON needs the page's session cookie; terms bar automated collection | `app.broker_registry`; official domains | **USE NOW\*** |
| NSE-2 | [Brokers' social handles](https://www.nseindia.com/trade/members-compliance/list-of-social-media-handle) (JSON `/api/list-of-social-media-handel`) | 582 rows of Facebook, Instagram, LinkedIn, X and YouTube links | As above | `social.official_handles` | **USE NOW\*** |
| NSE-3 | [SEBI-debarred entities](https://www.nseindia.com/static/regulations/member-sebi-debarred-entities) → `prs_ra_sebi.xls` | Order date, name, PAN, DIN/CIN, period; includes orders on social-media stock tips | XLS, 8.7 MB | `sebi.debarred` (PAN hashed at ingest) | **USE NOW\*** |
| NSE-4 | [Defaulter and expelled members](https://www.nseindia.com/static/complaints/defaulter-expelled-members) | Negative list of brokers | HTML | `caution.match` | USE NOW\* |
| NSE-5 | "Caution for Investors" press releases (`nsearchives.nseindia.com/web/pressrelease/…`) | Named persons, mobile numbers, Telegram/YouTube channels, websites (e.g. dabba operators) | PDF, curated by hand | `caution_entry` | **USE NOW** |
| NSE-6 | [Trade verification](https://www.nseindia.com/static/invest/first-time-investor-trade-verification) | Investors check their own trades at the exchange (T+1) | FORM | "Does your app's trade exist at the exchange?" | USE NOW (link) |
| NSE-7 | [ASM](https://www.nseindia.com/reports/asm) / [GSM](https://www.nseindia.com/reports/gsm) surveillance lists; daily bhavcopy | Stocks under surveillance; daily prices | CSV / zip; terms as above | Risk flag when a tip names a stock (review against the no-tips rule first) | LATER |
| NSE-8 | [Terms of use](https://www.nseindia.com/static/nse-terms-of-use) | Bars systematic collection and redistribution without permission | — | Constraint | — |
| BSE-1 | Caution press releases (PDF tables: name, mobile numbers, website, Play app, social links) and directories: [members](https://www.bseindia.com/members/MembershipDirectory.aspx), [authorised persons](https://www.bseindia.com/members/DirectoryOtherIntermediaries.aspx), [IA](https://www.bseindia.com/iara/IA_Member.aspx), [RA](https://www.bseindia.com/IARA/RegisteredRA.aspx), [IA/RA web links](https://www.bseindia.com/iara/weblink.aspx) | Negative lists; allow-lists | PDFs need a browser user agent and Referer; directories are JavaScript apps | `caution_entry`; deep links | **USE NOW** (curated) |
| BSE-2 | [Investor awareness programmes](https://www.bseipf.com/iap.html); NSE [equivalent](https://www.nseindia.com/static/invest/investors-awareness-programs) | Regional-language events; Investor Protection Fund | HTML | Track C, recovery | USE NOW (links) |

### 2.3 AMFI and the depositories

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| AMFI-1 | [ARN locator](https://www.amfiindia.com/locate-distributor) and negative lists ([suspended](https://www.amfiindia.com/locate-distributor/suspended-arn), `/invalid-arn`, [mis-selling](https://www.amfiindia.com/locate-distributor/list-of-arn-misselling)) | ARN, holder, validity, KYD flag, EUIN | Undocumented JSON `…/api/distributor-agent?strOpt=ALL&search=<ARN>&page=1&pageSize=10`; no key or CAPTCHA when tested | `amfi.arn` (one lookup per query) | **USE NOW** |
| AMFI-2 | [Fund houses' apps and handles](https://www.amfiindia.com/list-of-mobile-application) | Per AMC: SEBI registration, website, **email domain**, Android/iOS links, Facebook, Instagram, YouTube, X, LinkedIn, Telegram and **WhatsApp-group** links | HTML + "Download Excel" | `app.amc_registry`, `social.official_handles`, official domains | **USE NOW** |
| AMFI-3 | [NAVAll.txt](https://portal.amfiindia.com/spages/NAVAll.txt) and NAV history | ~18,100 schemes, `;`-separated (now with Plan and Option columns) | Terms: "personal and non-commercial use only"; no storing "any significant portion" | "Does this scheme exist?"; simulators only with permission | LATER (ask AMFI) |
| AMFI-4 | [Mutual Funds Sahi Hai](https://www.mutualfundssahihai.com/en) | Education in 9 languages; SIP and inflation calculators | Web | Track C links | USE NOW (links) |
| DEP-1 | CAS (consolidated account statement): [NSDL](https://nsdl.com/investor/know-your-cas), [CDSL](https://www.cdslindia.com/CAS/LoginCAS.aspx) | Every demat and MF holding, from the depository | Own account (PAN or CAS id + email) | "Trust your CAS, not a trading app's dashboard" | **USE NOW** (guidance) |
| DEP-2 | [NSDL SPEED-e](https://nsdl.com/investor-services-Speed-e-web), [CDSL easi](https://web.cdslindia.com/myeasitoken/Home/Login); brokers' voluntary trading freeze (SEBI, live 1 Jul 2024 [S]) | Freeze or unfreeze demat or trading access | Own-account login | Recovery script | **USE NOW** (links) |
| DEP-3 | [MF Central](https://www.mfcentral.com/) | All MF folios, CAS, unclaimed amounts | PAN + OTP | Recovery, education | USE NOW (link) |
| DEP-4 | DP lists ([CDSL](https://www.cdslindia.com/DP/dplist.aspx), [NSDL](https://nsdl.co.in/about/dps.php)) | DP names and ids | Cloudflare challenge; redirect loop for scripts | SEBI register already covers DPs | LATER |

### 2.4 RBI (Reserve Bank of India) and NPCI (National Payments Corporation of India)

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| RBI-1 | [NBFC lists](https://www.rbi.org.in/Scripts/BS_NBFCList.aspx): registered XLSX (as on 30 Jun 2026) and **cancelled-registration XLSX** | Lenders; a negative list | XLSX; `rbidocs` answers scripts with a JavaScript challenge, so download by hand quarterly | `rbi.nbfc` | **USE NOW** (manual) |
| RBI-2 | Directory of digital lending apps reported by regulated lenders (home-page link "DLA's deployed by Regulated Entities"; live since 1 Jul 2025, [PIB](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2241255&reg=3&lang=1)) | Every loan app RBI-regulated lenders report, "as is" | SAP BusinessObjects viewer; export not tested | `rbi.dla` | USE NOW (manual snapshot) |
| RBI-3 | [Alert List](https://rbidocs.rbi.org.in/rdocs/Content/PDFs/ALERTLIST10022023CC5FC4ACD619431497A56B6894188478.PDF) of unauthorised forex platforms | 95 entities after the 19 Nov 2025 update (names, websites); not exhaustive; 2026 updates UNVERIFIED | PDF behind a CAPTCHA; download by hand | `caution_entry` | **USE NOW** (manual) |
| RBI-4 | [Authorised electronic trading platforms](https://rbi.org.in/scripts/bs_viewcontent.aspx?Id=4080); [authorised dealers](https://rbi.org.in/commonman/English/Scripts/AuthorizedDealers.aspx) | Forex allow-list | HTML | `rbi.forex_allowlist` | **USE NOW** |
| RBI-5 | [Payment system operators](https://rbi.org.in/Scripts/PublicationsView.aspx?id=12043) | Wallets (PPIs) and payment aggregators with authorisation dates | HTML | `rbi.pso` | LATER |
| RBI-6 | `.bank.in` rule ([RBI/2025-26/28](https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=12837&Mode=0)) | Banks must use `.bank.in` (deadline 31 Oct 2025; IDRBT is the only registrar). Live: `hdfcbank.com` redirects to `hdfc.bank.in`; `.fin.in` for non-banks announced, status UNVERIFIED | Rule | `link.domain_rules`, official domains | **USE NOW** |
| RBI-7 | [Sachet](https://sachet.rbi.org.in) | Check whether an entity may take deposits; complaints about illegal schemes | Web | Deep link for deposit and Ponzi schemes | **USE NOW** (link) |
| RBI-8 | [CMS](https://cms.rbi.org.in/) (Ombudsman complaints; helpline 14448 [S]); [UDGAM](https://udgam.rbi.org.in/) (unclaimed deposits) | Grievances | Login | Recovery | **USE NOW** (links) |
| RBI-9 | [Financial Education](https://www.rbi.org.in/FinancialEducation/Home.aspx); [RBI Kehta Hai](https://rbikehtahai.rbi.org.in/) | Posters and films in 13 languages, "for banks and other stakeholders to download and use" | Downloads; Kehta Hai behind a CAPTCHA | Track C content | USE NOW |
| RBI-10 | [IFSC/MICR search](https://www.rbi.org.in/Scripts/IFSCMICRDetails.aspx) | Bank → branch drill-down | FORM only | Use the Razorpay mirror [G1] | — |
| RBI-11 | [DBIE](https://data.rbi.org.in/DBIE/) | Rates, CPI | Manual download | Simulator inputs | LATER |
| RBI-12 | [Disclaimer](https://www.rbi.org.in/Scripts/Disclaimer.aspx) | "caching and links to, and the framing of this Web Site… are prohibited" without written notice | — | **Write to RBI before production** | — |
| NPCI-1 | UPI members and third-party apps ([page](https://www.npci.org.in/product/upi/all-members); [Wayback copy, 25 Sep 2025](https://web.archive.org/web/20250925164656/https://www.npci.org.in/what-we-do/upi/3rd-party-apps)) | Handle → bank → app (PhonePe `@ybl/@ibl/@axl`, Google Pay `@okaxis/@okhdfcbank/@okicici/@oksbi`, Paytm `@paytm/@ptyes/@ptaxis/@pthdfc/@ptsbi`, about 37 apps) | JavaScript bot wall (403 to scripts); copy by hand | `psp_handle` table for `upi.psp` | **USE NOW** (manual) |
| NPCI-2 | Safety rules [S]: payee **core-banking (CBS) name** shown from 30 Jun 2025 (addendum to OC-101); person-to-person **collect requests ended 1 Oct 2025**; disputes go app → PSP bank → NPCI → RBI Ombudsman | Rules | Text | "Approve to receive money" = fraud; payee-name mismatch | **USE NOW** (rules) |
| NPCI-3 | UPI Help (AI assistant; pilot 8 Oct 2025 [S]) | Transaction status, complaints, AutoPay in English, Hindi, Telugu, Bengali | Via bank apps; no public URL | Recovery | LATER |
| NPCI-4 | UPI Linking Specification 1.6 (Nov 2017; [copy](https://www.labnol.org/files/linking.pdf)) | `upi://pay` parameters (`pa`, `pn`, `mc`, `tr`, `am`, `cu`, `url`, `mode`, `orgid`, `sign`…) and signing rules | PDF; newer tables are not public | `upi.qr` | **USE NOW** |

### 2.5 Other regulators and registries

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| IRDAI-1 | Licensed entities: [all](https://irdai.gov.in/list-of-licensed-insurance-entities), [brokers](https://irdai.gov.in/list-of-brokers), [corporate agents](https://irdai.gov.in/list-of-corporate-agents1), [web aggregators](https://irdai.gov.in/list-of-web-aggregators), [**telemarketers**](https://irdai.gov.in/list-of-telemarketer1) | Allow-lists | HTML with dynamic rows; export format UNVERIFIED | `irdai.entities` | LATER |
| IRDAI-2 | [Blacklisted agents](https://irdai.gov.in/list-of-black-listed-agents); agent locator | Negative list; licence lookup | Agency-portal host timed out (UNVERIFIED) | `caution_entry` | LATER |
| IRDAI-3 | [Bima Bharosa](https://bimabharosa.irdai.gov.in/) (grievances; 155255 [S]) | Complaints, unclaimed amounts | Login | Recovery | USE NOW (link) |
| IRDAI-4 | [Caution notice](https://irdai.gov.in/web/guest/document-detail?documentId=9808878) (Sep 2026) | A fake site impersonating Bima Bharosa | PDF | Seed bad domains | **USE NOW** |
| PFRDA-1 | [Registered intermediaries](https://pfrda.org.in/intermediaries/registered-intermediaries) | NPS points of presence, record keepers, pension funds, retirement advisers | HTML | `pfrda.intermediaries` | LATER |
| IFSCA-1 | [Directory](https://ifsca.gov.in/DirectoryList); [scam alerts](https://ifsca.gov.in/Pages/Contents/Alerts_Against_Possible_Scams) | GIFT City regulated entities; warnings about fake "IFSCA-regulated" claims [S] | HTML | `ifsca.directory` | LATER |
| MCA-1 | [MCA V3](https://www.mca.gov.in) company/LLP master data | Status by CIN or LLPIN, directors, capital | CAPTCHA; access without login switched off in Dec 2025 [S]; 403 to scripts | Deep link only | LATER |
| MCA-2 | [Company master data on data.gov.in](https://www.data.gov.in/catalog/company-master-data) | CIN, name, status, class, capital, registration date, state, ROC; one CSV per ROC | GODL licence; freshness UNVERIFIED (the reachable host is a sandbox) | `company.cin` (struck-off check) | LATER (download from India) |
| MCA-3 | [IEPF](https://www.iepf.gov.in/) | Unclaimed shares and dividends; claims are free and IEPFA backs no middlemen [S]; the look-alike `iepf.org.in` is not a government site | FORM | Rule: an "IEPF recovery agent" asking a fee is a red flag | **USE NOW** (rule + link) |
| GST-1 | [Search taxpayer](https://services.gst.gov.in/services/searchtp) | Legal name, status, filing | CAPTCHA; API only via a licensed GST Suvidha Provider [S] | Offline GSTIN check digit + deep link | USE NOW (format) |
| FIU-1 | [FIU-IND](https://fiuindia.gov.in/) registered virtual-asset providers (49 by Mar 2025 [S]) | Allow-list of crypto exchanges | Unreachable; publication UNVERIFIED | — | LATER |
| FIU-2 | PIB releases on FIU-IND notices: [1 Oct 2025](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2173758&reg=48&lang=2) (25 offshore VDA providers), [28 Dec 2023](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1991372&reg=48&lang=2) (9 incl. Binance, KuCoin) | Dated denylist; some later registered (e.g. Binance [S]) | HTML | `caution_entry` with dates | **USE NOW** |
| CRCS-1 | [CRCS](https://crcs.gov.in/) and the [Sahara refund portal](https://mocrefund.crcs.gov.in/) | Multi-state cooperative registry; the official refund route; look-alikes `sahararefundportal.net.in`, `sahararefunds.com` | HTML | Look-alike seeds; deposit-scheme checks | **USE NOW** |

### 2.6 Cybercrime, telecom and fact-checking

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| I4C-1 | [cybercrime.gov.in](https://cybercrime.gov.in) + helpline **1930** | Reporting; CFCFRMS alerts banks in the money trail and holds funds still in mule accounts ("golden hour") | Web / phone | First recovery step | **USE NOW** |
| I4C-2 | Check Suspect: [numbers, email, account, UPI](https://cybercrime.gov.in/Webform/suspect_search_repository.aspx); [websites and apps](https://cybercrime.gov.in/Webform/suspect_search_websites.aspx) | Public-complaint registry (not certified) | CAPTCHA; the full Suspect Registry is for banks only | Deep link | **USE NOW** (link) |
| I4C-3 | Money Restoration Module (`mrm-ncrp.mha.gov.in`, June 2026 [S]) | Claim money held after a complaint, using the 14-digit acknowledgement | Login | Recovery | USE NOW (link) |
| I4C-4 | Cyber Dost on [X](https://x.com/Cyberdost), [YouTube](https://www.youtube.com/@cyberdosti4c), [Telegram](https://t.me/s/cyberdosti4c) | Awareness posts and videos; reuse licence not found | Public | Track C links with credit | USE NOW |
| I4C-5 | [I4C press releases](https://i4c.mha.gov.in/press-release.aspx) | Warnings naming apps [S] | Unreachable from our network | App denylist seeds | LATER |
| I4C-6 | MHA procedure of 2 Jan 2026 [S] | Lien on the disputed amount, not a whole-account freeze; refunds under ₹50,000 without a court order; freeze lifted after 90 days without an order | Text | Recovery skill content | **USE NOW** |
| DOT-1 | [Sanchar Saathi](https://www.sancharsaathi.gov.in/): [Chakshu](https://sancharsaathi.gov.in/sfc/) (report fraud calls and messages), [TAFCOP](https://tafcop.sancharsaathi.gov.in) (SIMs in your name), [CEIR](https://ceir.sancharsaathi.gov.in) (lost phones), awareness PDFs such as InvestmentScam.pdf | Reporting and self-help | Web/app with OTP to your own number; no public API | Report actions; Track C | **USE NOW** (links) |
| DOT-2 | FRI (Financial Fraud Risk Indicator) and MNRL (revoked numbers); [DoT–SEBI MoU, 15 Apr 2026](https://www.dot.gov.in/static/uploads/2026/04/44d0101276df3d4250b6fa9af509e5a9.pdf) | Risk rating of mobile numbers | Shared only with regulated entities via DoT's Digital Intelligence Platform | Production route via SEBI/NSDL | LATER |
| TRAI-1 | SMS header rules ([TCCCPR amendment, 12 Feb 2025](https://trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf); [header prefixes](https://www.trai.gov.in/sites/default/files/2024-09/Detail_Header_Prefixes_16062020.pdf); [header portal](https://smsheader.trai.gov.in/)) | `XY-ABCDEF-S`: operator, circle, body ≤11 characters, suffix -P/-S/-T/-G; URLs and APKs in commercial SMS must be whitelisted since 1 Oct 2024 | Rules; portal needs email OTP | `sms.header` | **USE NOW** (rules) |
| TRAI-2 | Number series: [PR 91/2026](https://www.trai.gov.in/sites/default/files/2026-07/PR_No91of2026.pdf), [PR 135/2025](https://www.trai.gov.in/sites/default/files/2025-11/PR_No.135of2025.pdf), [PR 119/2026](https://www.trai.gov.in/sites/default/files/2026-09/PR_No119of2026.pdf) | `1600xx` for service/transactional calls by regulated entities (deadlines: banks 1 Jan 2026; large NBFCs, payments and small finance banks 1 Feb 2026; other RBI entities 1 Mar 2026; MFs/AMCs, PFRDA, IRDAI 15 Feb 2026; qualified stock brokers 15 Mar 2026; other SEBI intermediaries voluntary); `140xx` promotional only; `1601` for utilities and logistics | Rules | `phone.rules` | **USE NOW** (rules) |
| TRAI-3 | DND / NCPR: [UCC page](https://trai.gov.in/complain-or-report-against-ucc), DND app, dial 1909 | Report spam (within 7 days [S]) | App / SMS | Report action | USE NOW (links) |
| PIB-1 | [PIB Fact Check](https://factcheck.pib.gov.in/); [X](https://x.com/pibfactcheck); [Telegram preview](https://t.me/s/PIB_FactCheck); WhatsApp +91 8799711259 | Debunks of claims about the government (e.g. finance-minister deepfakes) | Submission portal with OTP and CAPTCHA; read on X/Telegram; no feed | Fake government-scheme claims; cite date and post URL | **USE NOW** (links) |
| CERT-1 | [CERT-In advisories](https://www.cert-in.org.in/s2cMainServlet?pageid=PUBADVLIST); report to incident@cert-in.org.in | Security advisories | HTML; no feed | Phishing reports | LATER |

### 2.7 Open data, statistics and public digital infrastructure

| Id | Source | Gives | Access · terms | Satark use | Fit |
|---|---|---|---|---|---|
| OGD-1 | data.gov.in API (`api.data.gov.in/resource/{id}?api-key=…` [S]) | Any catalogue resource as JSON/CSV | Free key; host unreachable from our network (UNVERIFIED) | Bulk pulls | LATER |
| OGD-2 | [NCRB](https://www.ncrb.gov.in/) Crime in India 2024 (6 May 2026 [S]) | 1,01,928 cybercrime cases (+17.9%); fraud 72.6% of them | PDF/Excel | Education statistics | USE NOW |
| OGD-3 | MoSPI eSankhyiki: API `https://api.mospi.gov.in`, [MCP server](https://mcp.mospi.gov.in/), [code (MIT)](https://github.com/nso-india/esankhyiki-mcp) | CPI, WPI, IIP, GDP; no key per the README | Unreachable from our network (UNVERIFIED) | Inflation for simulators | USE NOW if reachable |
| OGD-4 | Small-savings rates, Finance Ministry memorandum of 30 Sep 2026 [S] | Oct–Dec 2026: PPF 7.1%, NSC 7.7%, Sukanya Samriddhi 8.2%, SCSS 8.2%, POMIS 7.4% | — | "Safe benchmark" in simulator S2 | **USE NOW** |
| DPI-1 | [Bhashini](https://bhashini.gov.in/) | ASR, translation, TTS and OCR in 22 languages | Keys after approval by the Digital India Bhashini Division; docs say proof-of-concept use only; WAV preferred (`bhashini.ai` is not the government service) | Production speech path | LATER |
| DPI-2 | [AIKosh](https://aikosh.indiaai.gov.in/) | Indian datasets and models | Free sign-up; organisations need approval | Speech/text data | LATER |
| DPI-3 | [BharatGen on Hugging Face](https://huggingface.co/bharatgenai) | Param2-17B, FinanceParam (Apache-2.0), Shrutam-2 ASR, sooktam2 TTS | Open weights; licences vary | Explanations and voice, never verdicts | LATER |
| DPI-4 | DigiLocker, Account Aggregator, UIDAI | Approval or licence needed; each pulls in user PII | — | Avoid (no Aadhaar) | NOT USEFUL |
| NISM-1 | [NISM Skills Registry](https://www.nism.ac.in/nism-skills-registry) | Certificate check by the **candidate's PAN** only | Registration needed | Users won't have an adviser's PAN | NOT USEFUL |

---

## 3. Non-government APIs and data

Terms: an IOC (indicator of compromise) is a known-bad domain, URL, IP or file hash; CT (Certificate Transparency) logs record every public TLS certificate; an ASN (autonomous system number) identifies the network hosting an IP address.

### 3.1 URL, domain and certificate intelligence (A)

| Id | Source | Returns · access · free limits | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| A1 | [Phishing.Database](https://github.com/Phishing-Database/Phishing.Database) | Phishing domain, link and IP lists (ACTIVE, NEW-today, ALL): 497,247 domains, 784,405 links; no key; updated every few hours | MIT; a VirusTotal data vendor | `link.blocklist`, local | **USE NOW** |
| A2 | [Hagezi threat-intelligence feeds](https://github.com/hagezi/dns-blocklists) | 2,376,001 malicious domains; via jsDelivr; no key | GPL-3.0 (data used, not redistributed) | `link.blocklist`, local | **USE NOW** |
| A3 | [Spamhaus DBL](https://www.spamhaus.org/blocklists/domain-blocklist/) via the free Data Query Service | DNS lookup; 127.0.1.4 phishing, 127.0.1.5 malware; public resolvers are refused, so a DQS key is needed | Free for "non-commercial small organizations and individuals", ≤100,000 queries/day; use inside a service for third parties not addressed — confirm in writing | `link.spamhaus_dbl` | USE NOW after sign-up |
| A4 | [ThreatFox](https://threatfox.abuse.ch/api/) (abuse.ch) | IOCs with malware family; `POST https://threatfox-api.abuse.ch/api/v1/` (`search_ioc`, `search_hash`); Auth-Key | Free for not-for-profit use under fair use | `link.threatfox` | **USE NOW** |
| A5 | [MalwareBazaar](https://bazaar.abuse.ch/api/) (abuse.ch) | `get_info` by SHA-256/MD5/SHA-1 → file type, signature, tags; Auth-Key | As A4 | APK hash lookup (never upload the user's file) | USE NOW |
| A6 | [Cloudflare URL Scanner](https://developers.cloudflare.com/radar/investigate/url-scanner/) | Live scan: verdict, screenshot, redirects, certificates, contacted domains; free account token; 5,000 public scans/month, 1 per 10 s | Free; scans are public, so sanitise URLs | Only when local lists miss | USE NOW (sanitised) |
| A7 | [urlscan.io](https://urlscan.io/docs/api/) | Scans and search over past scans; generous daily quotas | "Only for your own personal use"; commercial or aggregated use needs written permission | — | LATER (ask) |
| A8 | [PhishStats](https://phishstats.info/) | Phishing URLs and scores as JSON; 50/day anonymous, 150 with a key | No redistribution of raw feeds | — | LATER |
| A9 | [OpenPhish community feed](https://openphish.com/phishing_feeds.html) | Phishing URLs every 12 h | Research use only; product use needs consent | — | NOT USEFUL |
| A10 | [Phishing Army](https://phishing.army/) | Aggregated domain list every 6 h | CC BY-NC 4.0; upstream terms may conflict | — | LATER (overlaps A1/A2) |
| A11 | [Cert Spotter API](https://sslmate.com/ct_search_api/) | Every trusted certificate for a domain; free 100 single-host queries/hour with an account | Free account needed for non-evaluation use | `link.cert_age` | LATER |
| A12 | crt.sh (`?q=DOMAIN&output=json`) | Same CT data; no key | No published terms; three test calls returned HTTP 502 | Fallback only | LATER |
| A13 | DNS over HTTPS JSON: [Cloudflare](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/), [Google](https://developers.google.com/speed/public-dns/docs/doh/json) | Live A/MX/NS/TXT records; no key (tested) | Free; rate limits undocumented; do not use for Spamhaus queries | `link.dns` | **USE NOW** |
| A14 | [IPinfo Lite](https://ipinfo.io/lite) | ASN, network name, country for an IP; token; "unlimited" free | CC BY-SA 4.0, attribution required | `link.hosting` | USE NOW |
| A15 | [WhoisDS newly registered domains](https://www.whoisds.com/newly-registered-domains) | Daily zip of names (70,000 on 1 Oct 2026, of which 557 `.in`; the free file looks capped, UNVERIFIED) | Reusable "including for commercial purposes" | Proactive look-alike hunting | LATER |
| A16 | [Tranco](https://tranco-list.eu/) | Top-1M domains averaged over 30 days; rank API 1/s | Cite Tranco; source licences vary | `link.popularity` | **USE NOW** |
| A17 | CrUX India top list ([mirror](https://github.com/zakird/crux-top-lists), `data/country/in/<YYYYMM>.csv.gz`) | 1,000,000 Indian origins in rank buckets, monthly; kite.zerodha.com, groww.in and hdfc.bank.in are in the top 1k | CrUX data CC BY 4.0 | `link.popularity`; brand look-alikes | **USE NOW** |
| A18 | Cloudflare Radar ranking API | Top-100 per country | CC BY-NC 4.0 | — | LATER (A17 covers it) |
| A19 | Google Web Risk | Commercial Safe Browsing; 100,000 lookups/month free, then paid | Billing account | Only if Satark becomes commercial | NOT USEFUL now |
| A20 | [Google Safe Browsing v5](https://developers.google.com/safe-browsing/reference) | `hashes.search` with 4-byte hash prefixes (private), `urls.search`, `hashList.get` | "For non-commercial use only" | `link.safe_browsing` | USE NOW |
| A21 | [VirusTotal public API](https://docs.virustotal.com/reference/public-vs-premium-api) | 500 requests/day, 4/min | "Must not be used in commercial products or services" | On-demand only, within quota | LATER |
| A22 | [URLhaus](https://urlhaus.abuse.ch/api/) (abuse.ch) | Malware URLs (not phishing); dumps every 5 minutes; Auth-Key required | Free for non-commercial use under fair use | `link.urlhaus`, local | USE NOW |
| A23 | PhishTank | Hourly dumps still downloadable a few times a day | "New user registration temporarily disabled" | — | NOT USEFUL now |
| A24 | RDAP via the [IANA bootstrap](https://data.iana.org/rdap/dns.json) | Domain registration dates; `.in` → `https://rdap.nixiregistry.in/rdap/` (tested: zerodha.in registered 2010-02-17) | Public protocol | `link.rdap_age` | **USE NOW** |

### 3.2 Official-domain baselines (B)

| Id | Source | Details | Licence | Satark use | Fit |
|---|---|---|---|---|---|
| B1 | [Wikidata](https://www.wikidata.org/wiki/Wikidata:Data_access) property P856 (official website) | SPARQL or entity JSON; a User-Agent is required. 12 of 18 Indian finance names had P856 (missing: Upstox, Motilal Oswal, ICICI Securities, SBI Funds; "Angel One" and "Dhan" matched wrong entities); 56 of 64 banks, already with `hdfc.bank.in`, `sbi.bank.in` | CC0 | Seed of `official_domain`, reviewed by hand | **USE NOW** |
| B2 | NSE brokers' app list | See [NSE-1]; Apple's `sellerUrl` adds official websites for most apps | NSE terms | Official domains | USE NOW\* |
| B3 | `.bank.in` / `.fin.in` | See [RBI-6] | Rule | `link.domain_rules` | **USE NOW** |
| B4 | A curated list of brokers' official domains | None exists; build it from B1, B2, iTunes `sellerUrl` and Play developer sites, then review | — | — | — |

### 3.3 Apps (C)

| Id | Source | Details | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| C1 | [iTunes Search/Lookup API](https://performance-partners.apple.com/search-api) | `https://itunes.apple.com/lookup?bundleId=…&country=in`; ~20 calls/min; no key. Tested: `com.zerodha.kite3` → seller "Zerodha Broking Limited", sellerUrl zerodha.com | Verification use not addressed (UNVERIFIED) | `app.itunes` | **USE NOW** |
| C2 | Google Play "SEBI verified" label | The details page `/store/apps/details?id=PKG&hl=en_IN&gl=IN` contains `aria-label="SEBI verified"` for Zerodha Kite, Angel One, Groww, Upstox and Dhan; absent for WhatsApp and with `gl=US`; translated with `hl=hi`. Badge needs SEBI registration and listing in an exchange app registry; launched March 2026 with ~600 apps | `robots.txt` allows `/store/apps/details`; no official API | `app.play_listing` | **USE NOW** (one fetch per check, cached) |
| C3 | [google-play-scraper](https://github.com/facundoolano/google-play-scraper) | `app()` uses the allowed details path; search, reviews and permissions use paths that robots.txt disallows | MIT; may break | Use `app()` only | LATER |
| C4 | [androguard](https://github.com/androguard/androguard) | Package name, permissions, signing-certificate digest from an APK; same name + different certificate = repackaged fake | Apache-2.0 | `apk.static` | LATER |
| C5–C8 | MobSF (see OSS-12); Koodous (free tier allows 0 analyses); Exodus Privacy (no keys for production apps); F-Droid (only open-source apps) | — | — | — | LATER / NOT USEFUL |

### 3.4 Phone numbers (D)

| Id | Source | Details | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| D1 | [libphonenumber](https://github.com/google/libphonenumber) (`phonenumbers` 9.0.40) | Offline parse, validate, type, region and *original* carrier (wrong after porting). Classifies `160[01]…` as MOBILE and `140…` as UAN; does not know 1930 | Apache-2.0 | `phone.rules` with our own overrides | **USE NOW** |
| D2 | TRAI number series and header suffixes | See [TRAI-1, TRAI-2] | Rules | `phone.rules`, `sms.header` | **USE NOW** |
| D3 | Twilio Lookup (line type) | $0.008 per request; India coverage UNVERIFIED; sends the number to a vendor | Commercial | — | NOT USEFUL |
| D4 | Truecaller developer platform | Only verifies your own users' numbers; no lookup API | — | — | NOT USEFUL |

### 3.5 Fact-checking and news (E)

| Id | Source | Details | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| E1 | [Google Fact Check Tools API](https://developers.google.com/fact-check/tools/api) | `claims:search` by query and language; key; Indian publishers (Alt News, BOOM, Factly, The Quint, Vishvas News, India Today) indexed; PIB Fact Check not seen (UNVERIFIED) | Google APIs terms | `news.factcheck` | LATER |
| E2 | [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | News search over 3 months; no key; ≤1 request per 5 s (HTTP 429 seen) | "Unlimited and unrestricted use… without fee"; cite GDELT | `news.factcheck` (queued, cached) | LATER |
| E3 | NewsAPI.org | Free plan for development only | — | — | NOT USEFUL |
| E4 | [Meedan Check](https://github.com/meedan/check-api) | Tipline platform; no public cross-publisher search | MIT | Partner with a fact-checker on Check | LATER |

### 3.6 Social platforms (F)

| Id | Source | Details | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| F1 | [YouTube Data API v3](https://developers.google.com/youtube/v3/docs/channels) | `channels.list`: creation date, country, subscriber count (rounded; can be hidden), video and view counts; 1 unit per call, 10,000 units/day; no verification-badge field | Developer policies | `social.youtube` | USE NOW |
| F2 | [Telegram Bot API](https://core.telegram.org/bots/api) 10.3 | `getChat("@channel")`: title, description, linked chat; `getChatMemberCount`; whether a non-member bot can read any public channel is UNVERIFIED | Free; bot token | `social.telegram` | USE NOW |
| F3 | Telegram client API (MTProto, e.g. Telethon) | Channel flags `verified`, `scam`, `fake`, creation date | Needs a user account; automation risks bans | `social.telegram_label` | LATER |
| F4 | Instagram Business Discovery | Followers and media count for business/creator accounts only; our own professional account and permissions needed | Meta terms | — | NOT USEFUL now |
| F5 | X API | No free tier ($0.005 per post read) | Paid | — | NOT USEFUL |

### 3.7 Payments (G)

| Id | Source | Details | Terms | Satark use | Fit |
|---|---|---|---|---|---|
| G1 | [Razorpay IFSC](https://github.com/razorpay/ifsc) (unofficial mirror of RBI and NPCI files) | Bank, branch, address, UPI/NEFT/RTGS/IMPS flags, MICR, SWIFT; release v2.0.62 (1 Sep 2026); also `https://ifsc.razorpay.com/{IFSC}` | Code MIT; dataset public domain | `bank.ifsc`, shipped offline | **USE NOW** |
| G2 | UPI handle → app/bank map | No maintained open dataset; build it from [NPCI-1] | — | `psp_handle` table | **USE NOW** (manual) |
| G3–G4 | Razorpay "Validate VPA", Cashfree UPI verification | Need a KYC'd merchant account and return the account holder's name (personal data) | Commercial | — | NOT USEFUL |

### 3.8 Market data for simulators (H)

| Id | Source | Details | Terms | Fit |
|---|---|---|---|---|
| H1 | NSE archives / bhavcopy | Daily prices | Terms bar automated collection and reproduction | LATER (permission or licence) |
| H2 | niftyindices.com index history | Index levels | Same restriction; index licensing is sold | LATER |
| H3 | BSE historical data | — | Terms page blocked to scripts (UNVERIFIED) | LATER |
| H4 | AMFI NAV history | See [AMFI-3] | Personal, non-commercial use | LATER |
| H5 | [mfapi.in](https://www.mfapi.in/) | NAV history per scheme as JSON; no auth | No licence; AMFI's terms apply to the data | LATER |
| H6 | Yahoo Finance via yfinance | Prices | "Personal use only" | NOT USEFUL |
| H7 | [OECD "Share Prices for India" via FRED](https://fred.stlouisfed.org/series/SPASTT01INM661N) | Monthly index (2015 = 100; Aug 2026 = 284.5); CSV without a key; always older than 30 days | "Copyrighted: citation required" | **USE NOW** for compounding and SIP lessons |
| H8 | Synthetic price paths | Geometric Brownian motion with index-like drift and volatility, labelled "illustrative" | No licensing exposure | **USE NOW** for leverage and F&O simulators |

### 3.9 Datasets for evaluation (I)

Hugging Face licences are whatever the uploader states, and synthetic data makes accuracy look better than it is. No verified corpus of Indian WhatsApp investment or stock-tip scams exists, so those eval messages are written by hand, starting from JaanchLo's investment family [OSS-6].

| Id | Dataset | Contents | Licence | Fit |
|---|---|---|---|---|
| I1 | [SMS Phishing Dataset](https://data.mendeley.com/datasets/f45bkkt8pr/1) (Mendeley) | 5,971 messages: 638 smishing, 489 spam, 4,844 ham | CC BY 4.0 | **USE NOW** |
| I2 | [PhiUSIIL Phishing URL Dataset](https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset) (UCI) | 235,795 URLs (100,945 phishing), 54 features | CC BY 4.0 | **USE NOW** |
| I3 | [SMS Spam Collection](https://archive.ics.uci.edu/dataset/228/sms+spam+collection) (UCI) | Classic spam/ham baseline, not Indian | CC BY 4.0 | LATER |
| I4 | [Indian scam SMS, synthetic and audited](https://huggingface.co/datasets/Ridham115/indian-scam-sms-synthetic-audited) | 1,580 rows in English, Hindi, Hinglish and romanised regional languages, with genuine look-alikes; no investment category | CC BY 4.0 | **USE NOW** (hard negatives) |
| I5 | [scam_ham_india_14_languages](https://huggingface.co/datasets/anmolshrivastav/scam_ham_india_14_languages) | 14,000 synthetic messages, 1,000 per language | MIT | USE NOW (smoke tests) |
| I6–I8 | CloveAI india-spam-sms (templated, low realism); Hinglish scam-call set (provenance undocumented); 120-message multilingual set | — | MIT / Apache-2.0 | LATER |

### 3.10 Speech and language providers (J)

| Id | Provider | Details | Fit |
|---|---|---|---|
| J1 | Azure AI Speech | Free tier: 5 h/month STT and 0.5M characters/month neural TTS; STT in 14 Indian locales | LATER |
| J2 | AWS Transcribe and Polly | Transcribe in 11 Indian locales; Polly only en-IN and hi-IN | LATER |
| J3 | Krutrim Cloud (Ola) | Free credits; "Data stays in India" | LATER |
| J4 | AI4Bharat open models | IndicConformer-600M ASR (MIT), IndicTrans2 (MIT), Indic Parler-TTS (Apache-2.0), IndicF5; 1–4.5 GB each; a GPU realistically needed | LATER (self-hosted path) |
| J5 | **Sarvam AI** | Saaras v4 STT (23 languages; accepts WhatsApp Ogg/Opus as is; `keyterms` such as "Demat", "SEBI"; ₹30/hour); Bulbul v3 TTS (11 languages, ₹30 per 10K characters); ₹100 free credits that never expire; starter limits 60 STT and 30 TTS requests/min | **USE NOW** (server fallback) |
| J6 | Browser Web Speech API (Chrome on Android) | Free; recognition sends audio to Google's servers; phone voices for 9 Indian languages; `getVoices()` can be empty at first | **USE NOW** (first choice, with fallback) |
| J7 | Bhashini | See [DPI-1] | LATER (production path) |

---

## 4. Useful but blocked, gated or commercial-only

| Source | Why not now | Route |
|---|---|---|
| SEBI Check, DNVS, cybercrime Check Suspect, GST search, MCA, IEPF | CAPTCHA or login | Deep links (LLD §9.10) |
| NPCI handle list | JavaScript bot wall | Copy by hand |
| DoT FRI and MNRL, I4C Suspect Registry, s.69A blocking lists | Regulated entities or law enforcement only; blocking orders are confidential | SEBI/NSDL partnership |
| NSE and BSE bulk data | Terms bar automated collection | Manual snapshots + written permission |
| RBI lists and pages | JavaScript challenge or CAPTCHA; disclaimer bars caching and framing | Manual download + letter to RBI |
| AMFI NAV data | Personal, non-commercial use only | Ask AMFI; synthetic data meanwhile |
| FIU-IND registered VDA providers | Site unreachable; publication unclear | PIB notices [FIU-2] |
| IRDAI agent locator, TRAI NCPR portal | Timed out | Retest from India |
| data.gov.in and MoSPI APIs | Unreachable from outside India | Retest from India |
| urlscan.io, OpenPhish, PhishTank | Personal-use terms, research-only terms, closed registration | — |
| Google Web Risk, Twilio Lookup, Koodous, X API, Razorpay/Cashfree VPA validation | Paid or need merchant KYC (and return personal names) | — |
| DigiLocker, Account Aggregator, UIDAI | Approval or licence; user PII | Avoid |
| NISM Skills Registry | Needs registration and the adviser's PAN | Not useful |

## 5. Permissions and emails to send

| To | Ask | Why |
|---|---|---|
| SEBI (website-policy contact) | Permission to reuse intermediary-register data with attribution; whether an official extract or API exists for the hackathon (also ask the organisers) | Core check; SEBI-11 |
| NSE | Permission to use the broker-app, social-handle and debarred lists | NSE-8 terms |
| RBI | Notice/permission for deep links and cached copies of the Alert List, NBFC and DLA lists | RBI-12 disclaimer |
| AMFI | Use of the ARN locator and NAV data in a public-good app | AMFI terms |
| Spamhaus | Whether free DQS covers a public-good service for third parties | A3 terms |
| urlscan.io (optional) | Written approval for scans inside Satark | A7 terms |

## 6. Still unverified

- NPCI's VPA length limits, current `mode`/`purpose` code tables and the BharatQR tag-26 layout.
- Bank account number lengths; the PAN check-letter algorithm; LLPIN, EPIC and passport formats from an official source.
- Whether the Telegram web preview shows SCAM/FAKE labels; whether a bot can `getChat` any public channel.
- Whether WhatsApp offers the Android share sheet for plain-text messages (test on a device).
- Freshness of data.gov.in company master data; reachability of MoSPI and data.gov.in APIs from India.
- SEBI-webscraper against today's SEBI site; PaRRVA public search; FIU-IND's registered list.
- Spamhaus ZRD in free DQS; Google Fact Check default quota; whether PIB Fact Check is in the ClaimReview index.
- CNAP (caller-name display) rollout status as of October 2026.
