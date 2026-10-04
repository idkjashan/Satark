"""Orchestrator: owns a check or chat run end to end (CONTRACTS §5, LLD §3.5).

A check: ingest (text, screenshot: OCR + local vision model, QR) -> rule pass (identifiers, checkers, phrase
rules, YAML score: the instant verdict) -> ROUTE:

- the rules are decisive (High risk proved by registry, official-list or threat-feed facts), or no model is
  configured: answer now, explanation from templates, through the guards;
- otherwise the agent loop (agent.py) investigates with tools (tools.py: Satark's checks, SEBI register search,
  web search over MCP...), the judge (assess.py) writes the assessment, the verifier keeps what is proved and the
  YAML scorer sets the level again (verdict revision 2, `ai_reviewed`).

When nothing risky was found, no identifier is present and both model calls agree the input is a question or
unrelated, the run hands off to the chat or gives the off-topic note: the model decides, never a keyword gate.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from satark.harness.budget import Budget
from satark.harness.events import EventBus, RunRegistry
from satark.harness.state import AskUser, CaseState, Explanation, PlanStep, ReasonText, Verdict

log = logging.getLogger(__name__)

MAX_ACTIVE_RUNS = 50
Emit = Callable[[str, dict], None]


@dataclass
class CheckInput:
    text: str | None = None
    image: bytes | None = None
    image_mime: str | None = None
    qr: str | None = None
    lang: str = "en"
    simple: bool = False
    client: str | None = None


@dataclass
class RunHandle:
    run_id: str
    case_id: str
    expires_at: datetime


class CaseExpired(Exception):
    """Raised by start_chat for an unknown or expired case_id. E maps it to 404 case_expired."""


class Busy(Exception):
    """Raised when active_runs() >= MAX_ACTIVE_RUNS. E maps it to 503 busy."""


class Orchestrator:
    def __init__(self, config, registry, pipeline, router, bus: EventBus, cases, planner, executor, joiner,
                 scorer, explainer, responder, vision_allowed: bool = False, assessor=None, agent=None,
                 vision=None) -> None:
        self.config = config
        self.assessor = assessor  # the judge (assess role); None or disabled = rules only
        self.agent = agent  # the check's agent loop (agent.AgentLoop); None = the judge alone
        self.vision = vision  # reads screenshots with a local vision model (vision.ImageReader); None = OCR only
        self.vision_allowed = vision_allowed  # legacy: send screenshots to the extract model (opt-in)
        self.registry = registry
        self.pipeline = pipeline
        self.router = router
        self.bus = bus
        self.cases = cases
        self.planner = planner
        self.executor = executor
        self.joiner = joiner
        self.scorer = scorer
        self.explainer = explainer
        self.responder = responder
        self.runs = RunRegistry()
        check = config.modes.get("check") or {}
        # A local model serves one request at a time: past `ai_concurrency` reviews in flight, a check waits at most
        # `ai_queue_wait_s` for a slot and otherwise answers from the rules alone (latency stays bounded under load).
        self._ai_slots = asyncio.Semaphore(int(check.get("ai_concurrency", 2)))
        self._trace: dict[str, dict] = {}  # case_id -> the running AI review's trace, until its done event
        self._ai_wait_s = float(check.get("ai_queue_wait_s", 15))

    def active_runs(self) -> int:
        return self.runs.count()

    # ---- public API (CONTRACTS §5) ---------------------------------------------------------
    async def start_check(self, inp: CheckInput) -> RunHandle:
        if self.active_runs() >= MAX_ACTIVE_RUNS:
            raise Busy()
        case = self.cases.new(lang=inp.lang, simple=inp.simple)
        run_id = secrets.token_urlsafe(16)
        self.bus.emit(run_id, "stage", {"stage": "received", "t_ms": 0})
        task = asyncio.create_task(self._run_check(run_id, case, inp))
        self.runs.add(run_id, task)
        return RunHandle(run_id=run_id, case_id=case.case_id, expires_at=case.expires_at)

    async def start_chat(self, case_id: str | None, message: str | None, choice: tuple[str, str] | None,
                          lang: str, simple: bool) -> RunHandle:
        if self.active_runs() >= MAX_ACTIVE_RUNS:
            raise Busy()
        case = None
        if case_id is not None:
            case = self.cases.get(case_id)
            if case is None:
                raise CaseExpired(case_id)
        if case is None:
            case = self.cases.new(lang=lang, simple=simple)
        else:
            case.lang, case.simple = lang, simple
        run_id = secrets.token_urlsafe(16)
        self.bus.emit(run_id, "stage", {"stage": "answering", "t_ms": 0})
        task = asyncio.create_task(self._run_chat(run_id, case, message, choice))
        self.runs.add(run_id, task)
        return RunHandle(run_id=run_id, case_id=case.case_id, expires_at=case.expires_at)

    # ---- check run ------------------------------------------------------------------------
    async def _run_check(self, run_id: str, case: CaseState, inp: CheckInput) -> None:
        # A chat on this case (its id is returned with the 202) waits until the check stops mutating it.
        async with self.cases.lock(case.case_id):
            await self._run_check_unlocked(run_id, case, inp)

    async def _run_check_unlocked(self, run_id: str, case: CaseState, inp: CheckInput) -> None:
        t0 = time.monotonic()
        emit: Emit = lambda type_, data: self.bus.emit(run_id, type_, data)  # noqa: E731
        try:
            limits = (self.config.modes.get("check") or {}).get("limits", {})
            new_budget = lambda: Budget(  # noqa: E731
                verdict_deadline_s=float(limits.get("verdict_deadline_s", 9)),
                run_deadline_s=float(limits.get("run_deadline_s", 12)),
                tool_calls=int(limits.get("tool_calls", 24)),
            )
            budget = new_budget()
            max_waves = int(limits.get("max_waves", 3))
            extract_wait_s = float(limits.get("extract_wait_s", 6))
            extract_on = self.router is not None and self.router.enabled("extract")

            text = inp.text or ""
            if inp.qr:
                self.pipeline.qr(case, inp.qr)

            extraction = None
            if inp.image and self.vision is not None and self.vision.enabled():
                # OCR (exact identifiers) and the local vision model (wording, layout, what is visible) together
                from satark.harness.state import ImageReading
                from satark.harness.vision import fuse, has_hindi

                emit("stage", {"stage": "reading_image", "t_ms": self._ms(t0)})
                mime = inp.image_mime or "image/jpeg"
                ocr_text = await self.pipeline.ocr(inp.image, mime)
                reading = await self.vision.read(inp.image, mime, transcribe=not has_hindi(ocr_text or ""))
                if reading is not None:
                    text = f"{text}\n{fuse(reading.visible_text, ocr_text or '')}".strip()
                    case.image = ImageReading(screen=reading.screen[:80], description=reading.description[:400],
                                              cues=[c[:60] for c in reading.cues[:5]])
                elif ocr_text:
                    text = f"{text}\n{ocr_text}".strip()
            elif inp.image:
                emit("stage", {"stage": "extracting", "t_ms": self._ms(t0)})
                # Privacy by default: the screenshot is read on our server (local OCR) and only the masked
                # text goes to a model. Sending the image itself to a vision model is opt-in
                # (SATARK_LLM_VISION=1), e.g. for a local model where the image never leaves the machine.
                if extract_on and self.vision_allowed:
                    extraction = await self._safe_llm_extract(self.pipeline.llm(case, image=inp.image, image_mime=inp.image_mime))
                else:
                    ocr_text = await self.pipeline.ocr(inp.image, inp.image_mime or "image/jpeg")
                    if ocr_text:
                        text = f"{text}\n{ocr_text}".strip()

            assess_on = self.assessor is not None and self.assessor.enabled()
            # Rule-based claims ("Reg. No. X" next to a name) stay on unless an extraction call will find them;
            # with the AI review on there is no text-extraction call, and the registry facts they enable decide.
            if inp.image:
                budget = new_budget()  # reading a screenshot can take seconds; the checks get their full time
            self._regex_extract(case, text, claims=not extract_on or assess_on)
            emit("entities", {"items": self._entity_items(case)})
            if case.image is not None:  # identifiers are known now: mask the model's words, show them unmasked
                from satark.harness import guards

                case.image.description = guards.mask(case.image.description, case)
                case.image.cues = [guards.mask(c, case) for c in case.image.cues]
                emit("image_reading", {"screen": case.image.screen,
                                       "description": guards.unmask(case.image.description, case, case.lang),
                                       "cues": [guards.unmask(c, case, case.lang) for c in case.image.cues]})

            if await self._merge_and_route(case, extraction, text, budget, emit):
                self._finish(run_id, case, self._timings(t0, verdict_ms=self._ms(t0), explain_ms=self._ms(t0)))
                return

            pending = None
            if text and extract_on and extraction is None and not assess_on:  # the AI review reads the text itself
                emit("stage", {"stage": "extracting", "t_ms": self._ms(t0)})
                pending = asyncio.create_task(self.pipeline.llm(case))

            wave_no = 0
            while wave_no < max_waves:
                steps = self.planner.plan(case, "check", budget)
                emit("plan", {"revision": case.plan.revision, "steps": self._plan_items(case)})
                emit("stage", {"stage": "executing", "t_ms": self._ms(t0)})
                async for ev in self.executor.run(steps, case, budget):
                    emit("check_result", self._check_result_item(ev, case))
                    if ev.derived_ids:
                        emit("entities", {"items": self._entity_items(case)})

                if pending is not None and pending.done():
                    extraction, pending = await self._safe_task_result(pending), None
                    if await self._merge_and_route(case, extraction, text, budget, emit):
                        self._finish(run_id, case, self._timings(t0, verdict_ms=self._ms(t0), explain_ms=self._ms(t0)))
                        return

                decision = self.joiner.decide(case, budget, pending is not None, len(steps), wave_no, max_waves)
                wave_no += 1
                if decision == "NEXT_WAVE":
                    continue
                if decision == "WAIT_EXTRACTION" and pending is not None:
                    wait_s = max(0.0, min(extract_wait_s, budget.verdict_left()))
                    try:
                        extraction = await asyncio.wait_for(pending, timeout=wait_s)
                    except Exception:  # timeout (wait_for already cancelled it) or the task itself failed
                        extraction = None
                    pending = None
                    if await self._merge_and_route(case, extraction, text, budget, emit):
                        self._finish(run_id, case, self._timings(t0, verdict_ms=self._ms(t0), explain_ms=self._ms(t0)))
                        return
                    continue
                break  # ASK_USER (case.question already set by the joiner) or FINISH

            if pending is not None:
                pending.cancel()
            extract_ms = self._ms(t0)

            case.verdict = self.scorer.score(case)
            assessment, routed = None, False
            if assess_on and not self.assessor.should_skip(case) and await self._ai_slot():
                try:
                    assessment, routed = await self._ai_review(case, text, budget, emit, t0)
                finally:
                    self._ai_slots.release()
                if routed:  # the model judged it a question (answered) or unrelated (off-topic note)
                    self._finish(run_id, case, self._timings(t0, verdict_ms=self._ms(t0), explain_ms=self._ms(t0)))
                    return
            else:
                emit("verdict", self._verdict_event(case))  # the rule-based answer (no model, busy, or nothing to add)
            verdict_ms = self._ms(t0)
            if case.question is None and not self._has_checkable(case):
                case.question = AskUser(question_id="type_details", text=self.config.t(case.lang, "ask.type_details"))
            if case.question is not None:
                emit("ask_user", {
                    "question_id": case.question.question_id, "text": case.question.text,
                    "options": [{"id": o.id, "label": o.label} for o in case.question.options],
                })

            emit("stage", {"stage": "explaining", "t_ms": self._ms(t0)})
            case.explanation = self._explanation_from(case, assessment) or (
                # the AI review owns the explanation: if it had none to give, templates (no second model call)
                self.explainer._template(case, fallback_used=True) if assess_on else await self._safe_explain(case))
            emit("explanation", {
                "summary": case.explanation.summary,
                "reasons": [{"code": r.code, "text": r.text} for r in case.explanation.reasons],
                "chips": case.explanation.chips, "fallback_used": case.explanation.fallback_used,
                "lang": case.explanation.lang,
            })
            self._finish(run_id, case, {
                "extract_ms": extract_ms, "verify_ms": extract_ms, "verdict_ms": verdict_ms, "explain_ms": self._ms(t0),
            }, trace=self._trace.pop(case.case_id, None))
        except Exception:
            log.exception("check run %s failed", run_id)
            emit("error", {"code": "internal", "retryable": True, "message_key": "error.internal"})

    async def _ai_slot(self) -> bool:
        try:
            await asyncio.wait_for(self._ai_slots.acquire(), timeout=self._ai_wait_s)
            return True
        except TimeoutError:
            log.warning("AI review skipped: %d reviews already running", int(self.config.modes.get("check", {}).get("ai_concurrency", 2)))
            return False

    # ---- the AI review (agent loop over the checkers; see satark/harness/assess.py) --------------
    async def _ai_review(self, case: CaseState, text: str, budget: Budget, emit: Emit, t0: float):
        """Plan -> execute -> assess (+verify) -> score -> (route). Returns (assessment, routed)."""
        from types import SimpleNamespace

        from satark.harness import verify

        if case.verdict.reasons or case.verdict.worth_noting or self._has_checkable(case):
            emit("verdict", self._verdict_event(case))  # revision 1: the instant rule-based answer
        emit("stage", {"stage": "reasoning", "t_ms": self._ms(t0)})
        msg = case.by_type("message.text")
        step = PlanStep(id=case.next_id("s"), checker_id="ai.assessment", entity_ids=[msg[0].id] if msg else [],
                        family="ai", status="running")
        case.plan.steps.append(step)
        case.plan.revision += 1

        def on_plan() -> None:
            emit("plan", {"revision": case.plan.revision, "steps": self._plan_items(case)})

        def on_evidence(ev) -> None:
            emit("check_result", self._check_result_item(ev, case))

        def give_up():
            step.status = "unknown"
            on_plan()
            emit("verdict", self._verdict_event(case))
            return None, False

        on_plan()
        plan_kind = None
        if self.agent is not None and self.agent.enabled():
            from satark.harness.context import Section
            from satark.harness.guards import brief
            from satark.harness.tools import ToolRun

            limits = (self.config.modes.get("check") or {}).get("limits", {})
            deadline = float(limits.get("agent_deadline_s", 40))
            run = ToolRun(case=case, mode="check", emit=emit, on_evidence=on_evidence, lang=case.lang, on_plan=on_plan,
                          budget=Budget(verdict_deadline_s=deadline, run_deadline_s=deadline,
                                        tool_calls=int(limits.get("tool_calls", 24))))
            known = len(case.entities)
            try:
                inv = await self.agent.investigate(run, lambda: [Section(brief(case, "assess", self.config), keep=True)],
                                                   int(limits.get("agent_steps", 3)), deadline)
                plan_kind = inv.kind
                self._trace[case.case_id] = {"steps": inv.steps, "stopped": inv.stopped, "lookups": len(inv.observations),
                                             "first_reading": inv.kind}
            except Exception:
                log.exception("agent loop failed; judging on the rule evidence alone")
            if len(case.entities) > known:  # names, handles or links the model pointed at
                emit("entities", {"items": self._entity_items(case)})
            on_plan()
        assessment = await self.assessor.assess(case, plan_kind)  # verified: only grounded factors remain
        case.verdict = self.scorer.score(case)  # the plan's extra checks count either way
        if assessment is None:
            return give_up()
        # What the input is counts only when the plan and the assessment, two separate model calls, agree
        # (or there was no plan): one call's slip cannot reroute a scam or set its rule findings aside.
        agreed = assessment.message_kind if plan_kind in (None, assessment.message_kind) else None
        if any(sig.code == "INJECTION_TEXT" for ev in case.ledger for sig in ev.signals):
            agreed = None  # the text addresses the model ("ignore your instructions..."): its reading of that text
            #                must not reroute the run or set the rule findings aside
        if not (case.verdict.reasons or case.verdict.worth_noting or assessment.risk_factors) and agreed:
            # Nothing risky found: a question goes to the chat, an unrelated request gets the off-topic
            # note. Never a keyword gate.
            judged = SimpleNamespace(is_question=agreed == "question", related_to_money=agreed != "unrelated")
            if await self._route_extraction(case, judged, text, budget, emit):
                step.status = "done"
                return None, True
        # Phrase-rule hits are set aside (never critical ones) for a warning or lesson: when both calls say so, or when
        # the judge says so and that the text asks the reader to do nothing, and the first call did not read a
        # request in it. Measured: official awareness posts (SEBI, PIB, I4C) were flagged by their own quoted phrases.
        harmless = assessment.message_kind == "awareness_or_lesson" and verify.asks_nothing(
            getattr(assessment, "asks_reader_to", None)) and plan_kind != "message_to_check"
        injected = any(sig.code == "INJECTION_TEXT" for ev in case.ledger for sig in ev.signals)
        set_aside = 0
        kind_used = not injected and (agreed == "awareness_or_lesson" or harmless) and assessment.message_kind == "awareness_or_lesson" \
            and not verify._names_counterparty(case, self.config)
        if not injected and (agreed == "awareness_or_lesson" or harmless):
            set_aside = verify.apply_message_kind(case, assessment, self.config)
        about_types = verify.about_scam_types(case, self.config) if kind_used else []
        if case.case_id in self._trace:
            self._trace[case.case_id].update(kept=len(assessment.risk_factors), dropped=getattr(assessment, "_dropped", 0),
                                             reading=assessment.message_kind)
        ev = verify.to_evidence(case, assessment.risk_factors, assessment)
        ev.step_id = step.id
        case.ledger.append(ev)
        step.status = "done"
        on_evidence(ev)
        on_plan()
        case.verdict = self.scorer.score(case)  # the model added grounded evidence; the rules still decide
        case.verdict.ai_reviewed = True
        if (assessment.scam_type or "") in {f"T{i}" for i in range(1, 18)} and case.verdict.level != "NO_SIGNS":
            case.verdict.scam_type = assessment.scam_type
            case.verdict.lesson = (self.config.scoring.get("lesson_by_scam_type") or {}).get(assessment.scam_type)
        # A story or awareness post about a scam: the level stays (normally NO_SIGNS), but the card says it describes a
        # known scam and links the lesson. Needs the awareness reading to have been used, and the text to describe a scam.
        if kind_used and (set_aside or assessment.risk_factors or assessment.scam_type
                          or getattr(assessment, "about_a_scam", False)):  # the judge's own yes/no: a 4B model often leaves scam_type empty on news
            stype = assessment.scam_type or (about_types[0] if about_types else None)
            case.verdict.about_scam = True
            case.verdict.scam_type = stype
            case.verdict.lesson = (self.config.scoring.get("lesson_by_scam_type") or {}).get(stype)
        emit("verdict", self._verdict_event(case))  # after the AI review
        return assessment, False

    def _template_chips(self, case: CaseState) -> list[str]:
        level = case.verdict.level if case.verdict else "UNKNOWN"
        keys = {"HIGH_RISK": ["chip.what_now", "chip.report_where"], "SUSPICIOUS": ["chip.how_verify_adviser", "chip.what_now"]}
        return [self.config.t(case.lang, k) for k in keys.get(level, ["chip.how_verify_adviser"])]

    def _explanation_from(self, case: CaseState, assessment) -> Explanation | None:
        """The assessment's summary, already guard-checked in its output validator, as the explanation."""
        if assessment is None or not (assessment.summary or "").strip():
            return None
        from satark.harness import guards

        reasons = [ReasonText(code=r.code, text=_reason_title(case, self.config, r.code)) for r in case.verdict.reasons]
        return Explanation(
            summary=guards.unmask(assessment.summary, case, case.lang),
            reasons=[ReasonText(code=r.code, text=guards.unmask(r.text, case, case.lang)) for r in reasons],
            chips=[c.strip() for c in assessment.chips if guards.chip_ok(c)][:3] or self._template_chips(case),
            fallback_used=False,
            lang=case.lang,
        )

    # ---- model-decided routing (see module docstring) --------------------------------------
    async def _route_extraction(self, case: CaseState, extraction, text: str, budget: Budget, emit: Emit) -> bool:
        if extraction is None or self._has_checkable(case):
            return False
        if getattr(extraction, "related_to_money", True) is False:
            case.verdict = Verdict(
                revision=(case.verdict.revision + 1) if case.verdict else 1, level="UNKNOWN", confidence="NOT_SURE",
                checked=[], actions=["type_details"], scoring_version=str(self.config.scoring.get("version", "")),
            )
            emit("verdict", self._verdict_event(case))
            case.question = AskUser(question_id="off_topic", text=self.config.t(case.lang, "ask.off_topic"))
            emit("ask_user", {"question_id": "off_topic", "text": case.question.text, "options": []})
            case.explanation = Explanation(summary=self.config.t(case.lang, "explain.off_topic"), lang=case.lang)
            emit("explanation", {"summary": case.explanation.summary, "reasons": [], "chips": [],
                                  "fallback_used": False, "lang": case.lang})
            return True
        if getattr(extraction, "is_question", False) is True:
            emit("stage", {"stage": "answering", "t_ms": 0})
            answer, refused = await self.responder.answer(case, text, None, budget, emit)
            emit("answer", {"text": answer.text, "cites": answer.cites, "actions": answer.actions,
                             "chips": answer.chips, "fallback_used": answer.fallback_used, "refused": refused})
            return True
        return False

    def _has_checkable(self, case: CaseState) -> bool:
        return any(e.type != "message.text" and not e.type.startswith("claim.") for e in case.entities)

    def _regex_extract(self, case: CaseState, text: str, claims: bool) -> list:
        try:
            return self.pipeline.regex(case, text, claims=claims)
        except TypeError:  # A's pipeline.regex() does not have the `claims` flag yet
            return self.pipeline.regex(case, text)

    # ---- LLM-path robustness: an extraction, merge, routing or explain problem must never ----
    # ---- fail the check run - it always has a deterministic path to fall back to. -----------
    async def _safe_llm_extract(self, call) -> object | None:
        try:
            return await call
        except Exception:
            log.exception("extraction LLM call failed; continuing without it")
            return None

    async def _safe_task_result(self, task: asyncio.Task):
        try:
            return task.result()
        except Exception:
            log.exception("background extraction task failed; continuing without it")
            return None

    async def _merge_and_route(self, case: CaseState, extraction, text: str, budget: Budget, emit: Emit) -> bool:
        """Merges a (possibly None) Extraction and applies model-decided routing. Returns True if
        the run is already finished. Any failure here just means "no extraction this round"."""
        if extraction is None:
            return False
        try:
            self.pipeline.merge(case, extraction)
        except Exception:
            log.exception("pipeline.merge failed; continuing without this extraction")
            return False
        emit("entities", {"items": self._entity_items(case)})
        try:
            return await self._route_extraction(case, extraction, text, budget, emit)
        except Exception:
            log.exception("model-decided routing failed; continuing with a normal check")
            return False

    async def _safe_explain(self, case: CaseState) -> Explanation:
        try:
            return await self.explainer.explain(case)
        except Exception:
            log.exception("explainer failed; using its template")
            return self.explainer._template(case, fallback_used=True)  # noqa: SLF001 (same owner, D)

    # ---- chat run -------------------------------------------------------------------------
    async def _run_chat(self, run_id: str, case: CaseState, message: str | None, choice: tuple[str, str] | None) -> None:
        emit: Emit = lambda type_, data: self.bus.emit(run_id, type_, data)  # noqa: E731
        try:
            limits = (self.config.modes.get("chat") or {}).get("limits", {})
            run_deadline = float(limits.get("run_deadline_s", 15))
            budget = Budget(verdict_deadline_s=run_deadline, run_deadline_s=run_deadline, tool_calls=int(limits.get("tool_calls", 8)))
            # start_chat() already emitted stage=answering before this task was even created
            async with self.cases.lock(case.case_id):
                answer, refused = await self.responder.answer(case, message, choice, budget, emit)
            self.cases.put(case)
            emit("answer", {"text": answer.text, "cites": answer.cites, "actions": answer.actions,
                             "chips": answer.chips, "fallback_used": answer.fallback_used, "refused": refused})
            emit("done", {"case_id": case.case_id, "timings": {}})
        except Exception:
            log.exception("chat run %s failed", run_id)
            emit("error", {"code": "internal", "retryable": True, "message_key": "error.internal"})

    # ---- small helpers ----------------------------------------------------------------------
    def _finish(self, run_id: str, case: CaseState, timings: dict, trace: dict | None = None) -> None:
        """`trace` (optional): how the AI review went (loop steps, why it stopped, lookups, the first reading,
        factors the verifier dropped), for monitoring and debugging; no message content."""
        self.bus.emit(run_id, "done", {"case_id": case.case_id, "timings": timings, **({"ai": trace} if trace else {})})
        self.cases.put(case)

    def _ms(self, t0: float) -> int:
        return int((time.monotonic() - t0) * 1000)

    def _timings(self, t0: float, **overrides: int) -> dict:
        now = self._ms(t0)
        base = {"extract_ms": now, "verify_ms": now, "verdict_ms": now, "explain_ms": now}
        base.update(overrides)
        return base

    def _verdict_event(self, case: CaseState) -> dict:
        from satark.harness.score import verdict_event

        return verdict_event(case, self.config)

    def _entity_items(self, case: CaseState) -> list[dict]:
        return [{"id": e.id, "type": e.type, "cls": e.cls, "display": e.display, "origin": e.origin} for e in case.entities]

    def _plan_items(self, case: CaseState) -> list[dict]:
        return [{"id": s.id, "checker_id": s.checker_id, "family": s.family, "status": s.status} for s in case.plan.steps]

    def _check_result_item(self, ev, case) -> dict:
        from satark.harness.proof import check_item

        return check_item(ev, case, self.config)


def _reason_title(case: CaseState, config, code: str) -> str:
    from satark.harness.score import _title

    return _title(case, config, code)


