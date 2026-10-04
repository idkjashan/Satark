"""The agent harness pieces: context fitting, the tool registry's policy, an MCP toolset over stdio, the
observe-think-act loop with a scripted model, and screenshot fusion. No network, no real model."""

from __future__ import annotations

import os
from collections import Counter
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from satark.config import Settings
from satark.harness import context
from satark.harness.budget import Budget
from satark.harness.context import Section
from satark.harness.orchestrator import CheckInput
from satark.harness.state import CaseState, Entity, Observation, utcnow
from satark.harness.tools import Call, MCPToolset, ToolRegistry, ToolRun, Toolset, ToolSpec
from satark.harness.vision import clean_ocr, fuse


# ---- context -------------------------------------------------------------------------------------------
def test_fit_trims_the_largest_trimmable_section_and_never_the_kept_ones():
    sections = [Section("task: decide", keep=True), Section("\n".join(f"old line {i}" for i in range(400))),
                Section("the message", keep=True)]
    out = context.fit(sections, budget=200)
    assert context.tokens(out) <= 200
    assert "task: decide" in out and "the message" in out
    assert "old line 399" in out and "old line 0\n" not in out  # older lines go first


def test_observations_render_newest_in_full_older_as_one_line():
    obs = [Observation(id="obs1", tool="web.search", text="first line\nmore detail", step=1),
           Observation(id="obs2", tool="satark.search_sebi_register", text="found: no\nclosest: X", step=2)]
    out = context.render_observations(obs, budget=500)
    assert "[obs1] web.search: first line" in out and "more detail" not in out
    assert "closest: X" in out


# ---- tool registry policy ----------------------------------------------------------------------------
class EchoTools(Toolset):
    name = "echo"

    def __init__(self):
        self.calls = []

    def specs(self):
        return [ToolSpec(name="echo.say", description="say", params={}, toolset="echo", modes=frozenset({"check"}),
                         max_calls=2)]

    def suggest(self, run):
        return [Call("echo.say", {"text": "a"}), Call("echo.say", {"text": "b"}), Call("echo.say", {"text": "c"})]

    async def call(self, spec, args, run):
        self.calls.append(args)
        return True, f"said {args['text']} near [UPI_1]"


def _case() -> CaseState:
    return CaseState(case_id="c1", expires_at=utcnow(), masked_text="pay [UPI_1] now")


def _run(case, mode="check", events=None) -> ToolRun:
    return ToolRun(case=case, mode=mode, budget=Budget(verdict_deadline_s=5, run_deadline_s=5, tool_calls=5),
                   emit=(lambda t, d: events.append((t, d))) if events is not None else (lambda t, d: None),
                   on_evidence=lambda ev: None)


async def test_registry_caps_dedupes_and_records_observations(config):
    echo = EchoTools()
    reg = ToolRegistry(config, [echo])
    case, events = _case(), []
    run = _run(case, events=events)
    assert len(reg.menu(run)) == 3
    obs = await reg.run([Call("echo.say", {"text": "a"}), Call("echo.say", {"text": "a"}),
                         Call("echo.say", {"text": "b"}), Call("echo.say", {"text": "c"})], run)
    assert [o.text for o in obs] == ["said a near [UPI_1]", "said b near [UPI_1]"]  # duplicate dropped, cap of 2
    assert [o.id for o in case.observations] == ["obs1", "obs2"]
    assert reg.menu(run) == []  # cap used up
    starts = [d for t, d in events if t == "tool_status" and d["status"] == "start"]
    ends = [d for t, d in events if t == "tool_status" and d["status"] == "end"]
    assert len(starts) == len(ends) == 2 and {d["call_id"] for d in starts} == {d["call_id"] for d in ends}
    assert reg.refusal(Call("echo.say", {"text": "z"}), _run(case, mode="chat")) == "not allowed here"
    assert reg.refusal(Call("nope.tool", {}), run) == "no such tool"


def test_external_tool_gets_public_identifiers_only(config):
    ts = MCPToolset("web", {"command": ["x"], "privacy": "external", "public_types": ["domain", "party.name"]})
    case = _case()
    case.entities = [
        Entity(id="e1", type="domain", cls="C", value=SecretStr("profitking-trade.in"), display="profitking-trade.in",
               placeholder="[DOMAIN_1]", origin="regex"),
        Entity(id="e2", type="upi.vpa", cls="C", value=SecretStr("profitking.desk@ybl"), display="profitking.desk@ybl",
               placeholder="[UPI_1]", origin="regex"),
        Entity(id="e3", type="party.name", cls="C", value=SecretStr("Rahul Sharma"), display="Rahul Sharma",
               placeholder="[NAME_1]", origin="regex", attrs={"kind": "person"}),
    ]
    assert ts.outgoing({"query": "[DOMAIN_1] scam [UPI_1] [NAME_1]"}, case) == {"query": "profitking-trade.in scam"}
    assert ts.outgoing({"query": "pay profitking.desk@ybl"}, case) is None  # a raw UPI ID typed by the model


async def test_mcp_toolset_over_stdio_with_the_fake_search_backend(config):
    os.environ["SATARK_WEBSEARCH_BACKEND"] = "fake"
    try:
        cfg = (config.tools["toolsets"]["web"])
        ts = MCPToolset("web", {**cfg, "env": {"SATARK_WEBSEARCH_BACKEND": "fake"}})
        await ts.start()
        try:
            assert [s.name for s in ts.specs()] == ["web.search"]
            case = _case()
            case.entities = [Entity(id="e1", type="domain", cls="C", value=SecretStr("profitking-trade.in"),
                                    display="profitking-trade.in", placeholder="[DOMAIN_1]", origin="regex")]
            run = _run(case)
            assert [c.args for c in ts.suggest(run)] == [{"query": "[DOMAIN_1]"}]
            ok, text = await ts.call(ts.specs()[0], {"query": "[DOMAIN_1] scam"}, run)
            assert ok and "profitking-trade.in scam" in text and "1." in text
        finally:
            await ts.close()
    finally:
        os.environ.pop("SATARK_WEBSEARCH_BACKEND", None)


# ---- the loop, with a scripted model, on the real runtime -------------------------------------------------
@pytest.fixture()
async def rt(fixture_db_path):
    from satark.harness.runtime import build_runtime, close_runtime

    runtime = await build_runtime(Settings.from_env(db_path=fixture_db_path, network=False, env={}))
    yield runtime
    await close_runtime(runtime)


def _scripted(steps: list[dict], judge: dict, seen: list | None = None) -> FunctionModel:
    """The n-th loop step gets steps[n] (or done), the judge call gets `judge`."""
    n = Counter()

    def fn(messages, info):
        tool = info.output_tools[0]
        props = tool.parameters_json_schema.get("properties", {})
        if "done" in props:
            n["step"] += 1
            if seen is not None:
                seen.append(" ".join(str(getattr(p, "content", "")) for m in messages for p in m.parts))
            out = steps[n["step"] - 1] if n["step"] <= len(steps) else {"thought": "", "done": True}
            out = {"thought": "", "pick": [], "web_search": "", "add": [], "done": True, "sender": "a stranger",
                   "asks_reader_to": "join a group", "message_kind": "message_to_check", **out}
        else:
            out = judge
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=out)])

    return FunctionModel(fn)


JUDGE = {"sender": "a stranger", "asks_reader_to": "join a group", "reasoning": "r", "message_kind": "message_to_check", "about_a_scam": True,
         "scam_type": None, "risk_factors": [],
         "summary": "Check before you pay.", "chips": []}


async def _events(rt, text: str) -> list[tuple[str, dict]]:
    h = await rt.orchestrator.start_check(CheckInput(text=text, lang="en", client="test"))
    return [(ev.type, ev.data) async for ev in rt.bus.subscribe(h.run_id)]


async def test_loop_picks_from_the_menu_observes_and_the_judge_can_cite_it(rt):
    seen: list[str] = []
    judge = {**JUDGE, "risk_factors": [{"code": "AI_RISK_PATTERN", "title": "The firm is not in SEBI's register.",
                                        "quote": "", "evidence_ids": ["obs1"]},
                                       {"code": "URGENCY", "title": "Pushes you to hurry.", "quote": "join today",
                                        "evidence_ids": []}]}
    rt.router.override("assess", _scripted([{"thought": "look the firm up", "add": [
        {"entity_type": "party.name", "value": "Sunrise Wealth Desk"}], "done": False}], judge, seen))
    events = await _events(rt, "Sunrise Wealth Desk gives sure-shot calls, join today")

    steps = [d for t, d in events if t == "agent_step"]
    assert steps[0]["step"] == 1 and steps[0]["thought"] == "look the firm up"
    assert [a["tool"] for a in steps[0]["actions"]] == ["satark.add_and_check"]
    assert "Possible lookups" in seen[0] and "Step 1 of" in seen[0]
    assert "[obs1]" in seen[1]  # step 2 observes what step 1 found
    verdict = [d for t, d in events if t == "verdict"][-1]
    assert verdict["ai_reviewed"] and verdict["level"] == "HIGH_RISK"  # a rule-found high (sure-shot) plus the grounded AI risk (now high)
    assert {"AI_RISK_PATTERN", "URGENCY"} <= {r["code"] for r in verdict["reasons"]} | set(verdict["worth_noting"])


async def test_loop_stops_at_its_step_budget_and_a_failing_step_still_gets_judged(rt):
    endless = [{"thought": "more", "web_search": "", "done": False}] * 10
    rt.router.override("assess", _scripted(endless, JUDGE))
    events = await _events(rt, "Hello, join our group for tips today")
    assert len([d for t, d in events if t == "agent_step"]) <= 2  # modes.yaml check agent_steps
    assert [d for t, d in events if t == "verdict"][-1]["ai_reviewed"] is True


async def test_an_unsafe_thought_is_not_shown(rt):
    rt.router.override("assess", _scripted([{"thought": "This message is safe and genuine.", "done": True}], JUDGE))
    events = await _events(rt, "Your SIP of Rs 5,000 is due on 5 Oct")
    assert [d for t, d in events if t == "agent_step"][0]["thought"] == ""


# ---- screenshots -------------------------------------------------------------------------------------
def test_ocr_cleanup_and_fusion_keep_exact_identifiers():
    model = "To withdraw, pay 15% tax first to UPI profiting.kingdesk@ybl. Register: www.profiting-trade.in"
    ocr = "+91 98765 43210\ntaxfirsttoUPlprofitking.desk@ybl.Offer\nRegister:www.profitking-\ntrade.in"
    assert "www.profitking-trade.in" in clean_ocr(ocr)  # a link broken across lines is joined
    out = fuse(model, ocr)
    assert "profitking.desk@ybl" in out and "www.profitking-trade.in" in out and "+91 98765 43210" in out
    hindi = "प्रिय ग्राहक, आपके खाते XX4821 से ₹1,200.00 डेबिट हुए। यह आप नहीं थे? कॉल करें 1800-123-4567"
    assert fuse("garbled reading", hindi) == hindi  # Hindi: the server's Devanagari OCR is the base text


async def test_screenshot_is_read_by_ocr_and_the_vision_role_and_shown(rt, monkeypatch):
    async def fake_ocr(image, mime):
        return "Pay 15% tax to UPlprofitking.desk@ybl today"

    monkeypatch.setattr(rt.orchestrator.pipeline, "ocr", fake_ocr)

    def vision(messages, info):
        tool = info.output_tools[0]
        args = {"screen": "WhatsApp chat", "visible_text": "Pay 15% tax to profiting.kingdesk@ybl today",
                "description": "A trading group admin asks for a tax before withdrawal.", "cues": ["profit chart"]}
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    rt.router.override("image", FunctionModel(vision))
    h = await rt.orchestrator.start_check(CheckInput(image=b"\x89PNG fake", image_mime="image/png", lang="en"))
    events = [(ev.type, ev.data) async for ev in rt.bus.subscribe(h.run_id)]
    reading = [d for t, d in events if t == "image_reading"][0]
    assert reading["screen"] == "WhatsApp chat" and reading["cues"] == ["profit chart"]
    upis = [e["display"] for t, d in events if t == "entities" for e in d["items"] if e["type"] == "upi.vpa"]
    assert "profitking.desk@ybl" in upis and "profiting.kingdesk@ybl" not in upis  # OCR's exact spelling won
    assert any(t == "stage" and d["stage"] == "reading_image" for t, d in events)


def test_case_level_memory_is_shared_across_runs():
    case = _case()
    run = _run(case)
    case.observations.append(Observation(id="obs1", tool="web.search", key="web.search:{}", text="x"))
    assert "web.search:{}" in run.done_keys()  # a later chat turn will not repeat a lookup the check made
    assert SimpleNamespace  # keep import used


def test_facts_about_an_entity_only_the_model_added_cannot_decide_high_risk(config):
    """Found on blind set 2: the model added the word "Console" as an app, the app check said "claims a broker but
    is not in NSE's list", and with the model's own claims that made High risk on a genuine IPO reminder."""
    from satark.harness.score import Scorer
    from satark.harness.state import Evidence, SignalHit, SourceRef

    case = _case()
    case.entities = [Entity(id="e9", type="app.package", cls="C", value=SecretStr("Console"), display="Console",
                            placeholder="[APP_1]", origin="llm")]
    case.ledger = [Evidence(id="ev1", step_id="s1", checker_id="apps.broker_list", family="app", entity_ids=["e9"],
                            status="hit", signals=[SignalHit(code="APP_CLAIMS_BROKER_NOT_LISTED", basis="official_list"),
                                                   SignalHit(code="REG_NOT_FOUND", basis="registry")],
                            source=SourceRef(id="nse"))]
    assert Scorer(config).score(case).level == "SUSPICIOUS"
    case.entities[0].origin = "regex"  # the same facts about an app the message itself named do decide
    assert Scorer(config).score(case).level == "HIGH_RISK"


# ---- reliability: circuit breaker and bounded concurrency -----------------------------------------------
def test_circuit_breaker_pauses_a_failing_role_and_closes_on_success(monkeypatch):
    from satark.harness import models

    router = models.ModelRouter({"breaker_failures": 3, "breaker_pause_s": 60}, {"SATARK_LLM": "test"})
    assert router.enabled("assess")
    for _ in range(3):
        router.record("assess", ok=False)
    assert not router.enabled("assess") and router.status()["assess"] == "paused after repeated failures"
    assert router.enabled("respond")  # only the failing role
    now = models.time.monotonic()
    monkeypatch.setattr(models.time, "monotonic", lambda: now + 61)
    assert router.enabled("assess")
    router.record("assess", ok=False)
    router.record("assess", ok=True)  # a success resets the count
    router.record("assess", ok=False)
    router.record("assess", ok=False)
    assert router.enabled("assess")


async def test_reviews_past_the_concurrency_limit_answer_from_the_rules(rt):
    import asyncio

    rt.orchestrator._ai_slots = asyncio.Semaphore(1)
    rt.orchestrator._ai_wait_s = 0.2

    async def slow(messages, info):
        await asyncio.sleep(1.0)
        tool = info.output_tools[0]
        props = tool.parameters_json_schema.get("properties", {})
        out = ({"thought": "", "pick": [], "web_search": "", "add": [], "done": True, "sender": "s", "asks_reader_to": "pay",
                "message_kind": "message_to_check"} if "done" in props else JUDGE)
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=out)])

    rt.router.override("assess", FunctionModel(slow))
    first, second = await asyncio.gather(_events(rt, "Join our VIP group for tips today"),
                                         _events(rt, "Join our VIP group for tips today"))
    reviewed = [[d for t, d in ev if t == "verdict"][-1]["ai_reviewed"] for ev in (first, second)]
    assert sorted(reviewed) == [False, True]  # one waited too long and got the rule verdict
