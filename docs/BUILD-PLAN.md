# Satark — how this build was run

This page records the delivery process for the hackathon build: how the work was split, the quality gates every
part had to pass, and the order of integration. The design itself is in `docs/reference/Satark-LLD.md`; the
binding interfaces are in `docs/CONTRACTS.md`.

## 1. Approach: contracts first, then parallel workstreams

1. **Contracts (M0).** Before any feature code, the shared interfaces were written and smoke-tested:
   domain models (`satark/harness/state.py`), the checker plugin API (`satark/checkers/base.py`,
   `registry.py`), the config loader with fail-closed validation (`satark/config.py`), the model router
   (`satark/harness/models.py`), the registry DB schema (`satark/ingest/schema.sql`), shared normalisers
   (`satark/infra/norm.py`), the registries (`config/*.yaml`), the HTTP/SSE contract and the content schemas
   (`docs/CONTRACTS.md`), and the shared test fixtures (`tests/conftest.py`, a fixture registry DB).
2. **Eight parallel workstreams**, each owning disjoint files and shipping its own tests:

| Stream | Owns | Proves itself with |
|---|---|---|
| A Extraction + guards | `satark/harness/extract/`, `guards.py`, `config/entities.yaml` | golden strings per entity type, PII-tripwire test, Hypothesis fuzzing |
| B Data + ingest | `satark/ingest/`, `config/sources.yaml`, `data/manual/` | parser and gate tests; a real build of `data/registry.db` |
| C1 Checkers (registry, payment, app, social) | `satark/checkers/{sebi,payment,apps,social}.py` | per-checker tests on the fixture DB; the generated contract test |
| C2 Checkers (link, phone, text) + HTTP | `satark/checkers/{link,phone,text}.py`, `satark/infra/http.py` | SSRF tests, lexicon tests (EN/HI/Hinglish), RDAP fixture |
| D Harness | planner, executor, joiner, scorer, explainer, responder, orchestrator | table-driven scorer tests, golden event order, FunctionModel tests |
| E API | `satark/app.py`, `satark/api/` | every endpoint × every error code, SSE replay |
| F PWA | `web/` | reducer, simulator and maths unit tests; type-check; bundle budget |
| G Content | `content/`, `skills/`, `tests/golden/cases.yaml` | schema, reachability and translation-completeness tests |

3. **Integration (M3).** Streams merged on the contracts; the full suite runs after each merge
   (regression), then the golden evaluation, the black-box API validation and the browser E2E tests.
4. **Hardening (M6).** Security and code review passes, load test, fixes, then documentation.
5. **AI-first harness (M7).** A third blind set showed the phrase rules had reached their limit (56% recall on new
   scam wording), so the check and the chat became model-driven harnesses: plan → execute → assess → verify →
   score for a check, plan → execute → answer → verify for chat (`satark/harness/assess.py`, `verify.py`,
   `respond.py`). Each change was measured on the blind set against a real local model (Ollama,
   `qwen2.5:3b-instruct`) and kept only if it raised recall without raising false alarms; the rule pass stays as
   the instant answer and the outage path.

## 2. Quality gates (definition of done)

| Gate | Command | Must be |
|---|---|---|
| Lint | `uv run ruff check satark tests scripts` | clean |
| Unit + contract + API tests | `uv run pytest -q` | all pass, no network |
| Golden evaluation | `uv run python -m tests.golden.test_golden` | HIGH_RISK recall ≥ 90%, false alarms ≤ 5% |
| Black-box endpoint validation | `uv run python scripts/validate_api.py` | every check passes |
| Browser E2E | `npm --prefix web run e2e` | all journeys pass |
| PWA build + budget | `npm --prefix web run build && npm --prefix web run size` | type-check passes; ≤ 150 KB gzipped |
| Load | `uv run python scripts/loadtest.py -n 50` | 0 errors; verdict p95 < 10 s |

## 3. Test layers

| Layer | What it proves |
|---|---|
| Unit | normaliser, every entity pattern, validators, masking/unmasking, scorer rules, joiner table, budget, simulators' maths |
| Contract (generated) | every registered checker: never raises, emits only declared codes, respects its timeout and privacy level, under DB-missing, timeout, 5xx and malformed-response conditions |
| Property-based (Hypothesis) | extraction never crashes on random Unicode; user data never survives masking |
| Harness | golden event order; LLM roles with `FunctionModel`/`TestModel` (no real model call can happen in tests); the AI review end to end with a scripted model: grounding, retries, the level cap, routing, model failure (`tests/unit/test_ai_review.py`) |
| API | status codes, error bodies, SSE framing and `Last-Event-ID` replay, rate limits, security headers |
| Golden evaluation | 47 realistic scam and legitimate messages in English, Hindi and Hinglish (plus 6 that need a model) |
| Blind sets | three sets of 60 messages written by evaluators who never saw the rules; `scripts/eval_set.py` runs any set with or without a model |
| E2E (Playwright) | the user journeys in a real browser against the real server |
| Load | 50 concurrent checks: deadlines, memory and error rate hold |

## 4. Scope cut for the sprint (versus the LLD)

Kept: the deterministic rule pass, 30+ checkers including all 19 MUST checkers, masking and guards, the AI-first
harness behind a switch (`SATARK_LLM`), the PWA with simulators S1–S3 and lessons, the report draft.
Deferred: the MCP server, server-side text-to-speech and speech-to-text, Telegram/WhatsApp
adapters, the nightly ingest job (the registry is rebuilt by hand with `python -m satark.ingest`).
