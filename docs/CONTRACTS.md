# Satark build contracts

This file is the single source of truth for interfaces between components. The design behind it is
`docs/reference/Satark-LLD.md` (LLD); where this file is simpler than the LLD, **this file wins**
(not built: an LLM planner, a TTS endpoint, channel adapters. MCP tools and the agent loop are built; see `docs/HARNESS.md`).

Rules for every contributor:

1. **Do not rename or remove anything named here** (module paths, class/function names, entity
   types, signal codes, event names, JSON fields, i18n key prefixes). Add freely.
2. **Edit only the files your task owns.** If you need a change in someone else's file, put it
   in your final report instead of editing it.
3. **Keep it small**: stdlib first, no new dependency unless unavoidable, no
   abstractions with one implementation, no speculative config.
4. **Every non-trivial piece ships with tests**, and tests never touch the network
   (`Settings(network=False)`, `respx`, fake checkers, PydanticAI `FunctionModel`/`TestModel`).
   Live-network tests are marked `@pytest.mark.network` and skipped unless `SATARK_NETWORK_TESTS=1`.
5. Python 3.12, `uv run pytest`, `uv run ruff check`. Do not run `uv add`/`uv sync` (deps are
   installed); if a dependency is missing, say so in your report.

## 1. Repository layout and owners

```text
satark/                      repo root (~/hackathon/satark)
  satark/
    config.py                Settings + Config loader/validator            [contracts, fixed]
    harness/state.py         domain models                                  [contracts, fixed]
    harness/models.py        ModelRouter                                     [contracts, fixed]
    checkers/base.py         checker protocol + helpers                      [contracts, fixed]
    checkers/registry.py     CheckerRegistry                                 [contracts, fixed]
    infra/db.py, infra/norm.py, ingest/schema.sql                           [contracts, fixed]
    harness/extract/*        normalise, regex, LLM extraction, merge         [A: extraction]
    harness/guards.py        mask/unmask/brief/output guards                 [A: extraction]
    ingest/*                 registry DB build (python -m satark.ingest)     [B: data]
    checkers/<family>.py     checker plugins                                 [C: checkers]
    infra/http.py            SafeHttpClient (SSRF guard)                     [C: checkers]
    harness/{budget,events,cases,plan,execute,join,score,explain,respond,
             skills,orchestrator,runtime}.py, satark/check.py (CLI)        [D: harness]
    api/*, app.py, harness/report.py                                         [E: api]
  config/*.yaml              registries (entities, signals, scoring, modes, models, languages, brands: contracts;
                             sources.yaml: B; phone_rules, claim_rules, lexicons/redflags.yaml: C;
                             lexicons/guards.yaml: A)
  content/                   shared with the PWA: i18n/, lessons/, sims/, faq.json, portals.json [G: content]
                             (i18n/ui.*.json belongs to F)
  skills/<area>/<name>/SKILL.md                                              [G: content]
  data/manual/               raw snapshots (+ .meta.yaml sidecars)            [B: data]
  data/registry.db           built by the ingest job (git-ignored)
  web/                       the PWA                                          [F: pwa]
  tests/conftest.py, tests/fixtures/fixture_db.py                            [contracts]
  tests/unit/test_<area>_*.py   per owner;  tests/contract/ (C);  tests/api/ (E);  tests/golden/ (G + QA)
```

## 1a. Design principle: AI-first harness, no fragile gates

Like real agent harnesses (Claude Code, the OpenAI Agents SDK, LangGraph), **the model decides intent and
semantics** — what kind of message this is (an offer, a routine notice, a warning, a question, unrelated), what
is worth looking up, which risks the wording shows — through typed outputs (`ReviewPlan`, `Assessment`, the
chat's plan and answer). **Deterministic code decides facts and the verdict**: identifier formats and checksums,
masking, registry lookups, threat lists, the verifier and the YAML scorer. Keyword rules never block or reroute
a user; they exist only as (a) the instant rule pass that answers first and keeps working in a model outage and
(b) the no-model fallback (FAQ answers, template explanations). Track C is first-class: a user can just ask or
learn (`/chat` with no case, lessons, simulators) without checking anything.

## 2. Core models (`satark/harness/state.py`)

Read the file; the important rules:

- `Entity.value` is a `SecretStr` holding the normalised raw value. Only checkers read it, via
  `CheckContext.raw(entity)`. U-class entities keep `value=""` (discarded at extraction).
- `Entity.display` is what the user sees (original text for C/P, `""` for U). Never put
  `display` or `value` into an LLM prompt: LLM input is built only by `guards.brief()`.
- Entity ids `e1, e2…`, step ids `s1…`, evidence ids `ev1…` come from `CaseState.next_id(prefix)`.
  Placeholders use the per-prefix counter too: `case.next_id("UPI")` → `UPI1` → placeholder `[UPI_1]`.
- Entities are deduplicated by `(type, norm_hash)`.
- R-class types are resolved at extraction: role `user` → U (masked, discarded); otherwise C.

## 3. Checker plugins (`satark/checkers/base.py`, `registry.py`)

A checker subclasses `BaseChecker`, is decorated with `@register_checker`, and lives in
`satark/checkers/<family>.py`. `check()` returns `hit(...)`, `clear(...)` or `unknown(...)`;
it may raise `TransientError` (executor retries once) — any other exception becomes `error`.

- `produces` must list **every** signal and flag code the checker can emit (contract-tested).
- `privacy`: `local` (nothing leaves the server), `public_only` (only a public id: domain,
  package id). A non-local checker may never consume a U- or R-class type (startup fails).
- `needs`: `"db"` (registry DB), `"http"`, `"secret:NAME"` (missing secret disables the checker).
- `source`: `config/sources.yaml` id (DB-backed) or a live-service id (`rdap`, `play`, `unshorten`);
  the executor uses it for the circuit breaker and the evidence's source chip (`SourceRef`).
- DB-backed checkers set `result.source = SourceRef(id=<source id>, as_on=ctx.db.source_as_on(<id>))`.
- An empty or missing source table → `unknown("source_missing")`, never a guess.
- `ctx.config` gives YAML registries (`ctx.config.brands`, `.phone_rules`, `.claim_rules`,
  `.lexicons["redflags"]`); `ctx.db` the registry DB; `ctx.http` the SafeHttpClient.

## 4. Extraction and guards (A) — interfaces used by D

```python
# satark/harness/extract/__init__.py exports ExtractorPipeline, Extraction, normalise_text
class ExtractorPipeline:
    def __init__(self, config: Config, router: ModelRouter | None = None, db: RegistryDB | None = None): ...
    def regex(self, case: CaseState, text: str) -> list[Entity]
        # normalise (NFKC, zero-width removal, Indic digits -> ASCII), find identifiers from
        # entities.yaml + deterministic claims (claim.impersonates from brands.yaml aliases,
        # party.name + claim.registered_as around a sebi.reg_no), resolve roles, discard U values,
        # add the `message.text` entity, append to case.entities (deduped), set case.masked_text.
        # Returns the NEW entities. Pure and fast (< 10 ms for 4,000 chars).
    def qr(self, case: CaseState, payload: str) -> list[Entity]      # a decoded QR string (upi://...)
    async def ocr(self, image: bytes, mime: str) -> str | None      # rapidocr fallback; None if unavailable
    async def llm(self, case: CaseState, image: bytes | None = None, image_mime: str | None = None) -> Extraction | None
        # the `extract` LLM role over case.masked_text (or the image). None if the role is off,
        # times out (router.timeout("extract")) or fails. Never raises.
    def merge(self, case: CaseState, extraction: Extraction) -> list[Entity]   # returns NEW entities
    def add_drafts(self, case: CaseState, drafts: list[EntityDraft], origin: Origin = "derived") -> list[Entity]
        # used by the executor for checker-derived entities (final URL, domain, VPA from a QR)

# satark/harness/guards.py
def mask(text: str, case: CaseState) -> str          # every known U/C surface value -> its placeholder
def unmask(text: str, case: CaseState, lang: str = "en") -> str   # C placeholders -> display; U -> "(hidden)"
def brief(case: CaseState, role: str, config: Config) -> str     # the ONLY LLM-input builder (JSON text)
def pii_leaks(prompt: str, case: CaseState) -> list[str]         # raw values found in an outgoing prompt
def check_output(text: str, case: CaseState, config: Config, lang: str,
                 expected_codes: list[str] | None = None) -> list[str]  # [] = pass; else problems
def is_advice_seeking(text: str) -> bool             # "which stock should I buy?" (en/hi/hinglish)
```

**Scope (model-decided, no keyword gates — product-owner decision).** Questions are never blocked by keyword
rules: they would be fragile and would stop legitimate "explain / teach me" questions. With the `respond`
role on, the model answers in-scope questions (checks, scams, recovery, rights, plain-language financial
education) and declines anything else, setting `ChatAnswer.refused` (`off_topic` or `advice`). In a check,
the AI review's `Assessment.message_kind` decides: `unrelated` with nothing risky and no identifiers → verdict
`UNKNOWN` and `ask_user {question_id: "off_topic"}`; `question` → the chat answers it (§5.1). The safety net is
on the output side: `check_output` rejects stock tips (recommendation forms only), code/markup, ungrounded
identifiers and "this is safe" wording; one retry for a chat answer, then the deterministic answer; for the AI
review, broken prose is replaced by templates and its grounded findings are kept. Without a model, chat answers
come from `content/faq.json` or `chat.fallback`.

`check_output` order (LLD §6.2): reason codes match `expected_codes` → no-tips patterns, recommendation
forms only ("you should buy…", "buy X at ₹…", "target ₹…", "stop loss…", "खरीद लो"…; never a bare "buy"),
from `config/lexicons/guards.yaml` → no code fences or markup →
grounding (every registration-number-like string and every `[XXX_n]` placeholder must exist in
the case) → forbidden affirmations ("is safe", "is genuine", "सुरक्षित है", "असली है") → script
(for `hi`, ≥60% of letters Devanagari) and length (summary ≤ 90 words).

## 5. Harness (D) — interfaces used by the API

```python
# satark/harness/orchestrator.py
@dataclass
class CheckInput:
    text: str | None = None; image: bytes | None = None; image_mime: str | None = None
    qr: str | None = None; lang: str = "en"; simple: bool = False; client: str | None = None

@dataclass
class RunHandle:
    run_id: str; case_id: str; expires_at: datetime

class CaseExpired(Exception): ...

class Orchestrator:
    async def start_check(self, inp: CheckInput) -> RunHandle       # returns at once; run continues in a task
    async def start_chat(self, case_id: str | None, message: str | None,
                         choice: tuple[str, str] | None, lang: str, simple: bool) -> RunHandle
                                                                    # raises CaseExpired for an unknown/expired case
    def active_runs(self) -> int

# satark/harness/events.py
class EventBus:
    def emit(self, run_id: str, type: str, data: dict) -> int        # returns the event id (1, 2, 3…)
    async def subscribe(self, run_id: str, after_id: int = 0) -> AsyncIterator[Event]
        # replays buffered events with id > after_id, then live ones; ends after "done" or "error"
    def exists(self, run_id: str) -> bool                             # False for unknown or purged runs

# satark/harness/runtime.py
@dataclass
class Runtime:
    settings: Settings; config: Config; registry: CheckerRegistry; db: RegistryDB | None
    http: SafeHttpClient; router: ModelRouter; bus: EventBus; cases: CaseStore
    orchestrator: Orchestrator; ready: bool; not_ready_reason: str | None
async def build_runtime(settings: Settings) -> Runtime   # fail closed on bad config (ConfigError)
async def close_runtime(rt: Runtime) -> None
```

`python -m satark.check "<text>" [--lang hi]` prints the event sequence (no server needed).

### 5.1 The agent harness (`agent.py`, `tools.py`, `assess.py`, `verify.py`, `respond.py`, `vision.py`)

Full design: [`docs/HARNESS.md`](HARNESS.md). With a model configured, a check is **rule pass → route → agent loop →
judge → verify → score**, and a chat turn is **pasted identifiers checked → agent loop → answer → verify**.

| Step | Who | Output |
|---|---|---|
| Rule pass | regex + checkers + YAML scorer | verdict revision 1 (instant; the outage answer) |
| Route | orchestrator | rules decisive (High risk, Sure) → template answer; else the loop |
| Loop step (≤ 2) | model, schema built per step: `thought`, `message_kind` (step 1 of a check), `pick` (menu ids), `web_search`, `add` (step 1), `done` | the tool registry runs the picks in parallel; results become observations `obs1…` on the case |
| Judge | model, `Assessment {reasoning, message_kind, scam_type, risk_factors[{code, title, quote, evidence_ids}], summary, chips}` | evidence ids may be checks (`ev…`) or observations (`obs…`); codes are an enum (text-judgement codes + `AI_RISK_PATTERN`) |
| Verify | `verify.ground` in the output validator | judgement codes need a quote or an observation, fact codes need check evidence; quoted factors need both calls to say `message_to_check`; none when every contact is official or the quote is a warning sentence |
| Score | YAML scorer | verdict revision 2 with `ai_reviewed: true`; model-only risks ≤ `ai_only_max_level` |

**Tools** (`config/tools.yaml`): toolsets `builtin` (Satark's `check_identifiers`, `add_and_check`,
`search_sebi_register`, `read_safety_note`) and `mcp_stdio` (any MCP server; `web` = `satark/mcp_servers/websearch.py`).
Each tool has `modes`, `max_calls`, `timeout_s`; a toolset with `privacy: external` receives only identifiers of its
`public_types` and must pass the PII tripwire. `GET /v1/meta` reports each toolset's status under `tools`.
Satark itself is an MCP server: `python -m satark.mcp_servers.satark_server` (`check_message`, `check_identifier`,
`search_sebi_register`).

**Screenshots**: on-server OCR (Latin model, plus the Devanagari model when `data/models/ocr-hi/` exists) and, when
`SATARK_LLM_IMAGE` names a model, a vision model's reading (`ImageRead {screen, visible_text, description, cues}`;
description only when OCR found Hindi). Text = the model's reading with identifiers spelled as OCR read them.

Local models get `native` output (JSON schema enforced while decoding) with field descriptions appended to the
instructions; hosted models get a final-answer tool call. Judgement roles run at temperature 0. Any model failure
leaves the rule verdict and a template explanation.

## 6. HTTP API (E)

Same origin as the PWA; no cookies; no CORS headers. Every non-2xx body is
`{"error": {"code": str, "message_key": str, "retryable": bool}}`.

| Method and path | Request | Success | Errors |
|---|---|---|---|
| `POST /v1/checks` | `multipart/form-data`: `text` (≤4,000 chars), `image` (JPEG/PNG/WebP ≤2 MB), `qr` (≤1,000), `lang` (enabled language, required), `simple` (`true`/`false`), `client` | `202 {run_id, case_id, events_url, expires_at}` | 413 `input_too_large`, 415 `unsupported_media`, 422 `nothing_to_check` / `bad_language`, 429 `rate_limited`, 503 `busy` / `not_ready` |
| `GET /v1/runs/{run_id}/events` | header `Last-Event-ID` (optional) | `200 text/event-stream` | 404 `run_not_found` |
| `POST /v1/chat` | JSON `{case_id?, message?, choice?: {question_id, option_id}, lang, simple?}`; message ≤1,000; no `case_id` = a fresh "ask or learn" conversation | `202 {run_id, case_id, events_url, expires_at}` | 404 `case_expired`, 422, 429, 503 |
| `POST /v1/practice` | JSON `{topic?, scam_type?, lang}`; `topic` = lesson id or free text (≤200), `scam_type` = T1..T17 | `200 {questions: [{question, options: [{id, text, correct}], explain, tactic?}], source: "model"\|"lessons", lesson}`: 3 questions in the PWA's `QuizQuestion` shape. Model role `practice`; output sanitised (placeholder phone/UPI/link, no "safe", no buy/sell advice), else static lesson quizzes | 413, 422 `bad_language`, 429, 503 |
| `POST /v1/report-draft` | JSON `{case_id, lang, answers: {when?, how_paid?, amount_band?}}` | `200 {text_en, text_lang, evidence: [{label, value}], portals: [{id, name, url, phone?}]}` | 404 `case_expired` |
| `GET /v1/meta` | — | `200 {sources: [{id, name, as_on, status, rows}], languages: [{code, name, native, speech}], disabled_checkers: [{id, reason}], llm: {role: status}, scoring_version, version}` | — |
| `POST /v1/feedback` | JSON `{case_id?, kind: "helpful"\|"mistake", level?, reason_codes?: []}` | `204` | 422 |
| `GET /healthz` | — | `200 {"status": "ok"}` | — |
| `GET /readyz` | — | `200 {"status": "ready", ...}` | `503 {"status": "not_ready", "reason"}` |
| `POST /share` | share-target fallback when the service worker is not active | `303` → `/check?text=<urlencoded text+url>` | — |
| `GET /*` | static PWA from `web/dist`; unknown non-API paths serve `index.html` | `200` | — |

Rate limits per client IP (in memory, never logged): checks 10/min, events 30/min, chat 20/min,
report 10/min, feedback 10/min. `SATARK_RATE_LIMIT_SCALE` multiplies the limits (`0` = off, for
tests and load runs). At most 50 active runs (`503 busy`). Security headers on every response:
`Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' blob: data:;
media-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none';
frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
`Permissions-Policy: camera=(self), microphone=(self), geolocation=()`.

### 6.1 SSE events (`GET /v1/runs/{run_id}/events`)

Each event: `id: <int>`, `event: <type>`, `data: <JSON>`. The server sends `retry: 2000` first,
a `: ping` comment every 10 s, and closes after `done` or `error`. A reconnect with
`Last-Event-ID: n` replays every event with `id > n` (kept until 5 minutes after the run ends).

| Event | Data |
|---|---|
| `stage` | `{stage: "received"\|"reading_image"\|"extracting"\|"planning"\|"executing"\|"reasoning"\|"scoring"\|"explaining"\|"answering", t_ms}` (`reasoning` = the agent loop and judge are running) |
| `image_reading` | `{screen, description, cues: [str]}` (what the vision model saw; identifiers shown as the user's own text) |
| `agent_step` | `{step, thought, actions: [{tool, label}]}` (one per loop step; `thought` ≤ 160 chars and guard-checked, may be empty; `label` is localized) |
| `entities` | `{items: [{id, type, cls, display, origin}]}` (`display` is `""` for U-class) |
| `plan` | `{revision, steps: [{id, checker_id, family, status}]}` |
| `check_result` | `{step_id, checker_id, family, status, signals: [code], source: {id, as_on}, stale, cached}` (the AI review's own result is `checker_id: "ai.assessment"`, `family: "ai"`) |
| `verdict` | `{revision, level, confidence, reasons: [{code, weight, title, source: {id, as_on}}], worth_noting: [code], assurances: [code], actions: [id], scam_type, simulator, sim_params: {rate, period}\|null (S2 pre-fill), lesson, checked: [{family, status}], scoring_version, ai_reviewed}` (an `AI_RISK_PATTERN` reason's title is the model's own verified sentence) |
| `explanation` | `{summary, reasons: [{code, text}], chips: [str], fallback_used, lang}` |
| `ask_user` | `{question_id, text, options: [{id, label}]}` (no options = free-text answer; `question_id` is `type_details`, `which_candidate` or `off_topic`) |
| `tool_status` | `{tool, status: "start"\|"end", label, call_id, ok?}` (`tool` is namespaced: `satark.check_identifiers`, `web.search`…; `call_id` pairs a start with its end; `ok` on end) |
| `answer` | `{text, cites: [evidence_id], actions: [id], chips: [str], refused: "off_topic"\|"advice"\|null, fallback_used}` (chat) |
| `done` | `{case_id, timings: {extract_ms, verify_ms, verdict_ms, explain_ms}}` |
| `error` | `{code, retryable, message_key}` |

Order: `verdict` precedes `explanation` and `ask_user`; `done` is last. With a model, a check usually emits two
verdicts: revision 1 from the rules (only when they found something or there is something to check), then the
AI-reviewed one (`ai_reviewed: true`) after `stage(reasoning)`. **Handoff:** when nothing risky was found, no
identifier is present and the assessment says the input is a `question`, the check run emits `answer` instead of
a final verdict; `unrelated` gives the off-topic `UNKNOWN` verdict and `ask_user(off_topic)`. `check_result` events
arrive in completion order. A chat run emits `stage(answering)`, `check_result`* and `tool_status`* for its lookups, `answer`,
optionally a new `verdict` (higher `revision`) if evidence changed the level, then `done`.
All text in events (titles, summary, answer) is already in the request's language and already
unmasked for display (C-class values shown, U-class never).

## 7. Content shared with the PWA (G, F)

### 7.1 i18n (`content/i18n/<part>.<lang>.json`, flat `{key: text}`)

`content.<lang>.json` (G; server + PWA) key prefixes:

| Key | Meaning |
|---|---|
| `signal.<CODE>` | one plain sentence, ≤ 12 words, for every risk/assurance/info code in `config/signals.yaml` |
| `family.<family>` | checklist row label (registry, payment, link, app, phone, text, social) |
| `level.<LEVEL>.headline` / `level.<LEVEL>.say` | card headline / the sentence read aloud |
| `confidence.<SURE\|FAIRLY_SURE\|NOT_SURE>` | "We are sure" … |
| `action.<id>` / `portal.<id>` | button labels / portal names |
| `scam_type.<T1..T11>` | short scam-type names |
| `entity.<type>` | entity labels ("UPI ID", "Website link") |
| `explain.*` | template-explanation sentences, e.g. `explain.uncertainty`, `explain.could_not_check` (`{families}`) |
| `chip.*` | follow-up question chips |
| `ask.type_details`, `ask.which_candidate`, `ask.off_topic` | ask_user texts |
| `chat.advice_refusal`, `chat.off_topic`, `chat.paused`, `chat.partial`, `chat.fallback` | fixed chat replies |
| `report.*` | complaint-draft template lines (placeholders in `{braces}`) |
| `source.<id>` | short source names for the evidence chips ("SEBI register") |

`ui.<lang>.json` (F; PWA only): keys prefixed `ui.`.
Placeholders use Python/JS-compatible `{name}` braces. Amounts use `en-IN` grouping (1,00,000).

### 7.2 Lessons (`content/lessons/<id>.json`)

```json
{"id": "compounding", "icon": "📈", "minutes": 2,
 "title": {"en": "...", "hi": "..."},
 "steps": [{"text": {"en": "...", "hi": "..."}, "visual": "compounding-chart"}],
 "analogy": {"en": "...", "hi": "..."},
 "quiz": {"question": {"en": "...", "hi": "..."},
          "options": [{"id": "a", "text": {"en": "...", "hi": "..."}, "correct": true}],
          "explain": {"en": "...", "hi": "..."}}}
```
Lesson ids used by `scoring.yaml`: `compounding`, `leverage`, `sebi-registration`, `fake-apps`,
`tips-and-pumps`. `visual` is optional and names a built-in PWA visual.

### 7.3 Simulators (`content/sims/S1.json`, `S2.json`, `S3.json`)

S1 is a finite-state machine (LLD §23.1–23.2):

```json
{"id": "S1", "kind": "fsm", "version": 1, "start": "invite",
 "title": {"en": "..."}, "vars": {"balance": 0, "lost": 0},
 "states": {
   "invite": {"say": {"en": "..."}, "choices": [
       {"id": "check", "label": {"en": "..."}, "to": "checked"},
       {"id": "join", "label": {"en": "..."}, "to": "deposit"}]},
   "deposit": {"say": {"en": "..."}, "choices": [
       {"id": "pay", "label": {"en": "..."}, "to": "profits", "set": {"lost": "+10000", "balance": "+10000"}}]},
   "checked": {"end": "safe", "reveal": {"en": "..."}}},
 "quiz": {"question": {"en": "..."}, "options": [{"id": "a", "text": {"en": "..."}, "correct": true}]}}
```
`set` operations: `+N`, `-N`, `=N`, `*F` only (no expressions). `end`: `safe` | `lost`.
Text may use `{balance}` / `{lost}` (formatted `en-IN`). S2 (`kind: "returns"`) and S3
(`kind: "leverage"`) hold texts and default parameters; the maths lives in the PWA:
S2 value = P × (1 + r)^n with n = 250 trading days / 52 weeks / 12 months per year;
S3 equity = margin × (1 + leverage × index return) on a seeded illustrative path.

### 7.4 Offline chat answers (`content/faq.json`)

```json
{"intents": [{"id": "verify_adviser",
              "patterns": ["verify", "registered", "genuine", "asli", "असली", "रजिस्टर्ड"],
              "answer": {"en": "...", "hi": "..."}, "actions": ["verify_sebi_register"],
              "chips": {"en": ["..."], "hi": ["..."]}}],
 "fallback": {"answer": {"en": "...", "hi": "..."}, "chips": {"en": ["..."], "hi": ["..."]}}}
```

### 7.5 Skills (`skills/<area>/<name>/SKILL.md`)

YAML front matter `name`, `description`, `languages`, `reviewer`, `reviewed_on`, `sources`,
`reason_codes`; Markdown body ≤ 400 words, facts only, each with its source. Names referenced
by `config/signals.yaml` must exist, plus `policy/no-tips`, `policy/tone-for-seniors`,
`policy/uncertainty`.

## 8. Testing conventions

- Shared fixtures in `tests/conftest.py`: `config` (validated=False), `fixture_db` (a
  `RegistryDB` over a temp SQLite built by `tests/fixtures/fixture_db.py`), `make_case()`.
- Golden messages: `tests/golden/cases.yaml` (G writes, QA runs):
  `{id, lang, text, expect: {level, codes_any: [], codes_all: [], codes_none: []}, note}`.
- Fuzz tests use Hypothesis (`@given`) with `max_examples` ≤ 200 so the suite stays under ~60 s.
