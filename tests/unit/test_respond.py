"""Responder: plan -> execute -> answer -> verify, model-decided scope, deterministic fallback (LLD §6.3).

Uses `FakeGuards` (monkeypatched over `respond._guards`), not the real `guards.check_output`:
a content bug found during development (`no_tips.en` had two `(?i)` flags joined by `|`, which
Python 3.11+ rejects with `re.error` on every call - since fixed upstream) made every LLM answer
"fail" validation for the wrong reason. These tests are about D's wiring, not A's content, so
fakes stay the right choice regardless.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import satark.harness.respond as respond_mod
from satark.harness.agent import AgentLoop
from satark.harness.execute import DagExecutor
from satark.harness.models import ModelRouter
from satark.harness.plan import RulePlanner
from satark.harness.respond import Responder
from satark.harness.score import Scorer
from satark.harness.skills import SkillStore
from satark.harness.state import CaseState, EntityDraft, utcnow
from satark.harness.tools import SatarkTools, ToolRegistry
from tests.unit.harness_fakes import FakeChecker, FakeGuards, FakePipeline, make_registry


def _responder(config, checkers=(), faq=None, pipeline=None, router=None, search=None) -> tuple[Responder, FakePipeline]:
    pipeline = pipeline or FakePipeline()
    registry = make_registry(*checkers)
    planner = RulePlanner(registry, config)
    executor = DagExecutor(registry, config, pipeline, network=True)
    scorer = Scorer(config, registry)
    skills = SkillStore(config.root / "skills")
    responder = Responder(router, config, registry, None, planner, executor, pipeline, skills, scorer, faq or {})
    satark = SatarkTools({}, config, registry, executor, pipeline, skills, search or (lambda name, cat: []))
    responder.tools = ToolRegistry(config, [satark])
    responder.agent = AgentLoop(router, config, responder.tools, role="respond")
    return responder, pipeline


def _case(lang: str = "en") -> CaseState:
    return CaseState(case_id="c1", lang=lang, expires_at=utcnow() + timedelta(minutes=30))


def _router(model=None) -> ModelRouter:
    r = ModelRouter({}, {})
    if model is not None:
        r.override("respond", model)
    return r


def _budget():
    from satark.harness.budget import Budget

    return Budget(verdict_deadline_s=15, run_deadline_s=15, tool_calls=8)


def _is_plan(info: AgentInfo) -> bool:
    return "done" in info.output_tools[0].parameters_json_schema.get("properties", {})


def _out(info: AgentInfo, step=None, **fields) -> ModelResponse:
    """A loop step gets `step` (default: nothing to look up, done); the answer call gets `fields`."""
    if _is_plan(info):
        args = {"thought": "the user asks something", "pick": [], "web_search": "", "add": [], "done": True, **(step or {})}
    else:
        refused = fields.pop("refused", None)
        request = {"off_topic": "not_about_money", "advice": "stock_tip_request"}.get(refused or "", "money_or_scam_question")
        args = {"request": request, "text": "", "chips": [], "actions": [], "cites": [], **fields}
    return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])


def _prompt_text(messages) -> str:
    return " ".join(str(getattr(p, "content", "")) for m in messages for p in m.parts)


async def test_coding_question_is_refused_off_topic_with_the_reviewed_text(config, monkeypatch):
    """The model classifies the request; for an unrelated one the reply is the reviewed decline, never the model's
    own words (measured: a 3B model asked to decline still told the joke)."""
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())

    def fn(messages, info):
        return _out(info, text="def sort(xs): return sorted(xs)", refused="off_topic")

    faq = {"fallback": {"answer": {"en": "x"}, "chips": {"en": ["What can you check?", "What is SIP?"]}}}
    responder, _ = _responder(config, faq=faq, router=_router(FunctionModel(fn)))
    answer, refused = await responder.answer(_case(), "write me a python function to sort a list", None,
                                               _budget(), lambda t, d: None)

    assert refused == "off_topic"
    assert answer.text == config.t("en", "chat.off_topic") and "def " not in answer.text
    assert len(answer.chips) >= 2


async def test_educational_question_is_one_plan_and_one_answer_call(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    calls = {"plan": 0, "answer": 0}

    def fn(messages, info):
        calls["plan" if _is_plan(info) else "answer"] += 1
        return _out(info, text="SIP means investing a fixed amount every month, like a recurring deposit.",
                    actions=["lesson_compounding"])

    responder, _ = _responder(config, router=_router(FunctionModel(fn)))
    answer, refused = await responder.answer(_case(), "what is SIP?", None, _budget(), lambda t, d: None)

    assert calls == {"plan": 1, "answer": 1}  # fixed call count: no open-ended tool loop
    assert refused is None
    assert answer.actions == ["lesson_compounding"]


async def test_pasted_identifier_is_checked_before_the_model_and_rescored(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())

    async def hit_upi(entity, ctx):
        from satark.checkers.base import hit

        return hit("UPI_PERSONAL_WHILE_CLAIMING_SEBI")

    checker = FakeChecker("upi.fake", family="payment", consumes=frozenset({"upi.vpa"}),
                           produces=frozenset({"UPI_PERSONAL_WHILE_CLAIMING_SEBI"}), run=hit_upi)
    pipeline = FakePipeline(regex_drafts=[EntityDraft(type="upi.vpa", value="scammer@ybl")])
    order: list[str] = []

    def fn(messages, info):
        order.append("model")
        return _out(info, text="This looks risky: it asks for payment to a personal UPI ID.", actions=["dont_pay"])

    responder, _ = _responder(config, checkers=[checker], pipeline=pipeline, router=_router(FunctionModel(fn)))
    events: list[tuple[str, dict]] = []

    def emit(t, d):
        order.append(t)
        events.append((t, d))

    answer, refused = await responder.answer(_case(), "Pay scammer@ybl to join our VIP tips group!", None, _budget(), emit)

    assert order.index("check_result") < order.index("model")  # facts first, then the model reads them
    assert refused is None and "risky" in answer.text
    verdict_events = [d for t, d in events if t == "verdict"]
    assert len(verdict_events) == 1 and verdict_events[0]["level"] in ("SUSPICIOUS", "HIGH_RISK")


async def test_plan_lookup_runs_and_reaches_the_answer_prompt(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    searched: list[str] = []
    answer_prompts: list[str] = []

    def search(name, category):
        searched.append(name)
        return [{"reg_no": "INA000012345", "name": "Asha Advisors", "category": "IA", "valid": True, "similarity": 0.97}]

    def fn(messages, info):
        if not _is_plan(info):
            answer_prompts.append(_prompt_text(messages))
        return _out(info, step={"add": [{"entity_type": "party.name", "value": "Asha Advisors"}]},
                    text="SEBI's register lists a close match; confirm the registration number with them.")

    responder, _ = _responder(config, router=_router(FunctionModel(fn)), search=search)
    answer, _ = await responder.answer(_case(), "is Asha Advisors registered?", None, _budget(), lambda t, d: None)

    assert searched == ["Asha Advisors"]
    assert "INA000012345" in answer_prompts[0]
    assert "register" in answer.text


async def test_model_failure_gives_the_deterministic_answer(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())

    def fn(messages, info):
        raise RuntimeError("model server down")

    faq = {"fallback": {"answer": {"en": "I can check a message, link, UPI ID or help you learn."}, "chips": {}}}
    responder, _ = _responder(config, faq=faq, router=_router(FunctionModel(fn)))
    answer, refused = await responder.answer(_case(), "hello?", None, _budget(), lambda t, d: None)

    assert refused is None
    assert answer.fallback_used is True
    assert answer.text == faq["fallback"]["answer"]["en"]


async def test_bad_output_retries_then_falls_back_to_deterministic(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards(lambda text: ["no_tips"]))
    calls = {"answer": 0}

    def fn(messages, info):
        if not _is_plan(info):
            calls["answer"] += 1
        return _out(info, text="Buy XYZ at ₹500, target ₹650.")

    faq = {"fallback": {"answer": {"en": "I can check a message, link, UPI ID or help you learn."}, "chips": {}}}
    responder, _ = _responder(config, faq=faq, router=_router(FunctionModel(fn)))
    answer, refused = await responder.answer(_case(), "some chit chat", None, _budget(), lambda t, d: None)

    assert calls["answer"] == 2  # one retry, per router.agent()'s default retries=1
    assert "Buy XYZ" not in answer.text
    assert answer.fallback_used is True
    assert answer.text == faq["fallback"]["answer"]["en"]


async def test_unknown_action_id_retries_then_succeeds(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    calls = {"answer": 0}

    def fn(messages, info):
        if _is_plan(info):
            return _out(info)
        calls["answer"] += 1
        action = "not_a_real_action" if calls["answer"] == 1 else "lesson_compounding"
        return _out(info, text="Here is a lesson.", actions=[action])

    responder, _ = _responder(config, router=_router(FunctionModel(fn)))
    answer, refused = await responder.answer(_case(), "teach me about compounding", None, _budget(), lambda t, d: None)

    assert calls["answer"] == 2
    assert answer.actions == ["lesson_compounding"]


async def test_faq_path_with_no_model(config):
    faq = {
        "intents": [{"id": "verify_adviser", "patterns": ["verify", "registered"],
                     "answer": {"en": "Check SEBI's register yourself."}, "actions": ["verify_sebi_register"],
                     "chips": {"en": ["What is SEBI Check?"]}}],
        "fallback": {"answer": {"en": "I can check a message, link, UPI ID or help you learn."}, "chips": {}},
    }
    responder, _ = _responder(config, faq=faq, router=None)
    answer, refused = await responder.answer(_case(), "how do I verify my adviser?", None, _budget(), lambda t, d: None)

    assert refused is None
    assert answer.text == "Check SEBI's register yourself."
    assert answer.actions == ["verify_sebi_register"]


async def test_no_model_new_identifier_gets_checked(config):
    async def clear_fn(entity, ctx):
        from satark.checkers.base import clear

        return clear()

    checker = FakeChecker("upi.fake", family="payment", consumes=frozenset({"upi.vpa"}), run=clear_fn)
    pipeline = FakePipeline(regex_drafts=[EntityDraft(type="upi.vpa", value="legit@okaxis")])
    responder, _ = _responder(config, checkers=[checker], pipeline=pipeline, router=None)

    events: list[tuple[str, dict]] = []
    answer, refused = await responder.answer(_case(), "legit@okaxis", None, _budget(), lambda t, d: events.append((t, d)))

    assert refused is None
    assert any(t == "check_result" for t, _ in events)
    assert answer.fallback_used is False


class _StubRouter:
    def __init__(self, route):
        self.route = route

    async def classify_async(self, text):
        return self.route


class _StubKnowledge:
    def __init__(self, chunks):
        self.chunks = chunks

    async def search_async(self, q, k=4):
        return self.chunks

    async def best_async(self, q):
        return self.chunks[0] if self.chunks else None


def _chunk(cid="faq:verify_adviser", en="Check SEBI's register yourself."):
    from satark.harness.knowledge import Chunk

    return Chunk(id=cid, source="faq", ref="verify_adviser", text={"en": en}, index_text=en)


async def test_router_off_topic_refuses_without_calling_the_model(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    calls = []
    responder, _ = _responder(config, router=_router(FunctionModel(lambda m, i: calls.append(1) or _out(i, text="x"))))
    responder.scope_router = _StubRouter("off_topic")
    answer, refused = await responder.answer(_case(), "tell me a joke", None, _budget(), lambda t, d: None)
    assert refused == "off_topic" and calls == [] and answer.text == config.t("en", "chat.off_topic")


async def test_router_overrides_model_self_label_for_a_money_question(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    prompts = []

    def fn(messages, info):
        if not _is_plan(info):
            prompts.append(_prompt_text(messages))
        return _out(info, refused="off_topic", text="SIP is a fixed monthly investment.", cites=["K1", "K9"])

    responder, _ = _responder(config, router=_router(FunctionModel(fn)))
    responder.scope_router = _StubRouter("money_or_scam_question")
    responder.knowledge = _StubKnowledge([_chunk()])
    answer, refused = await responder.answer(_case(), "what is a SIP?", None, _budget(), lambda t, d: None)
    assert refused is None and "SIP" in answer.text
    assert answer.cites == ["faq:verify_adviser"]  # K1 mapped to the real id; invented K9 dropped
    assert "K1 (faq): Check SEBI's register yourself." in prompts[0]


async def test_no_retrieval_hit_never_refuses(config, monkeypatch):
    monkeypatch.setattr(respond_mod, "_guards", lambda: FakeGuards())
    responder, _ = _responder(config, router=_router(FunctionModel(lambda m, i: _out(i, text="General guidance."))))
    responder.knowledge = _StubKnowledge([])
    answer, refused = await responder.answer(_case(), "what is a bond?", None, _budget(), lambda t, d: None)
    assert refused is None and answer.text == "General guidance."


async def test_model_failure_with_checkable_entity_but_no_signals_answers_from_retrieval(config):
    """ch-08: a failed model step must not end in a bare 'no strong risk signs' headline."""
    pipeline = FakePipeline(regex_drafts=[EntityDraft(type="upi.vpa", value="x@ybl")])
    responder, _ = _responder(config, pipeline=pipeline, router=None)
    responder.knowledge = _StubKnowledge([_chunk(en="A VIP tips group is a classic trap.")])
    answer, _ = await responder.answer(_case(), "Is a VIP tips group normal?", None, _budget(), lambda t, d: None)
    assert answer.text == "A VIP tips group is a classic trap."
    assert answer.cites == ["faq:verify_adviser"]
