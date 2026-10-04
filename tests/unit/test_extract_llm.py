"""The `extract` LLM role: Extraction schema, extract()/merge() via FunctionModel, timeouts,
failures and the PII tripwire (CONTRACTS §4, LLD §7 step 7-8, build steps 7-8)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from satark.harness.extract import llm
from satark.harness.extract.pipeline import ExtractorPipeline
from satark.harness.models import ModelRouter

FIXED_ARGS = {
    "language": "en",
    "is_question": False,
    "related_to_money": True,
    "ocr_text": None,
    "ocr_confidence": "ok",
    "entities": [
        {"type": "upi.vpa", "value": "Scammer@YBL", "role": "payee", "quote": "pay to Scammer@YBL now"},
        {"type": "party.name", "value": "Rajesh Sharma", "role": "claimed_entity", "quote": "adviser Rajesh Sharma"},
    ],
    "claims": [
        {"type": "claim.guaranteed_return", "attrs": {"phrase": "guaranteed"}, "refs": [], "quote": "guaranteed 10% returns"},
        {"type": "claim.registered_as", "attrs": {"regulator": "SEBI", "category": "IA"}, "refs": ["Rajesh Sharma"], "quote": "SEBI registered"},
    ],
}


def _function_model(calls: list, args: dict | Exception = FIXED_ARGS, sleep: float = 0.0):
    async def fn(messages, info: AgentInfo) -> ModelResponse:
        calls.append(messages)
        if sleep:
            await asyncio.sleep(sleep)
        if isinstance(args, Exception):
            raise args
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(fn)


@pytest.fixture()
def router() -> ModelRouter:
    return ModelRouter({"roles": {"extract": {"timeout_s": 6}}}, env={})


async def test_extract_returns_fixed_extraction(config, make_case, router):
    calls: list = []
    router.override("extract", _function_model(calls))
    case = make_case()
    case.masked_text = "pay [UPI_1] now, guaranteed 10% returns, adviser [NAME_1] SEBI registered"
    extraction = await llm.extract(case, config, router)
    assert extraction is not None
    assert len(calls) == 1
    assert extraction.entities[0].value == "Scammer@YBL"
    assert extraction.claims[0].type == "claim.guaranteed_return"


async def test_extract_returns_none_when_router_is_none(config, make_case):
    case = make_case()
    assert await llm.extract(case, config, None) is None


async def test_extract_returns_none_when_role_not_configured(config, make_case, router):
    # no override, no SATARK_LLM env: the role has no model
    case = make_case()
    assert await llm.extract(case, config, router) is None


async def test_extract_returns_none_on_model_error(config, make_case, router):
    calls: list = []
    router.override("extract", _function_model(calls, args=RuntimeError("provider down")))
    case = make_case()
    case.masked_text = "hello"
    assert await llm.extract(case, config, router) is None


async def test_extract_returns_none_on_timeout(config, make_case):
    router = ModelRouter({"roles": {"extract": {"timeout_s": 0.05}}}, env={})
    calls: list = []
    router.override("extract", _function_model(calls, sleep=0.3))
    case = make_case()
    case.masked_text = "hello"
    assert await llm.extract(case, config, router) is None


async def test_raw_pii_that_slipped_into_masked_text_never_reaches_the_model(config, make_case, router):
    """Defense in depth: brief() re-masks masked_text (a U-class rescan), and pii_leaks() still guards
    the outgoing prompt, so a raw Aadhaar that slipped past extraction never reaches the model."""
    calls: list = []
    router.override("extract", _function_model(calls))
    case = make_case()
    case.masked_text = "aadhaar 234123412346 needs KYC update"  # a raw, valid-Verhoeff aadhaar
    await llm.extract(case, config, router)
    sent = " ".join(str(getattr(p, "content", "")) for messages in calls for m in messages for p in m.parts)
    assert "234123412346" not in sent


def test_merge_creates_entities_and_resolves_refs(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    case.masked_text = "pay [UPI_1] now"
    extraction = llm.Extraction.model_validate(FIXED_ARGS)
    new = pipe.merge(case, extraction)
    assert any(e.type == "upi.vpa" and e.origin == "llm" for e in new)
    vpa = next(e for e in case.entities if e.type == "upi.vpa")
    assert vpa.value.get_secret_value() == "scammer@ybl"  # normalised (lower)
    assert vpa.attrs.get("psp_handle") == "ybl"  # derive() still runs for llm-origin entities
    name = next(e for e in case.entities if e.type == "party.name")
    claim = next(e for e in case.entities if e.type == "claim.registered_as")
    assert claim.refs == [name.id]  # "Rajesh Sharma" ref resolved by name, not placeholder
    guaranteed = next(e for e in case.entities if e.type == "claim.guaranteed_return")
    assert guaranteed.origin == "llm"


def test_merge_keeps_failed_checksum_with_valid_false(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    extraction = llm.Extraction.model_validate(
        {**FIXED_ARGS, "entities": [{"type": "aadhaar", "value": "234123412340", "role": "user", "quote": "x"}]}
    )
    pipe.merge(case, extraction)
    ent = next(e for e in case.entities if e.type == "aadhaar")
    assert ent.valid is False
    assert ent.value.get_secret_value() == ""  # still U-class: discarded regardless of validity


def test_merge_ocr_text_runs_regex_and_masks(config, make_case):
    pipe = ExtractorPipeline(config)
    case = make_case()
    extraction = llm.Extraction.model_validate(
        {**FIXED_ARGS, "entities": [], "claims": [], "ocr_text": "pay scanner@okaxis, otp 482913"}
    )
    pipe.merge(case, extraction)
    assert any(e.type == "upi.vpa" for e in case.entities)
    assert "482913" not in case.masked_text


def test_merge_none_is_a_no_op(config, make_case):
    """Regression (integration bug report): the orchestrator (LLD §3.5) merges whatever
    pipeline.llm() returned without checking for None first - `extract.merge(case,
    pending.result())` - and llm() returns None whenever the role is off, times out, fails or
    is PII-blocked. merge(case, None) must return [] rather than raising AttributeError."""
    pipe = ExtractorPipeline(config)
    case = make_case()
    pipe.regex(case, "pay scammer@ybl now")  # a prior entity, to confirm nothing is touched
    before = list(case.entities)
    assert pipe.merge(case, None) == []
    assert case.entities == before


async def test_extract_then_merge_none_end_to_end(config, make_case, router):
    """The exact failing shape from integration: a disabled/None-returning role feeding
    straight into merge(), as the orchestrator does."""
    case = make_case()
    case.masked_text = "hello"
    extraction = await llm.extract(case, config, router)  # no override: role is off -> None
    assert extraction is None
    assert llm.merge(ExtractorPipeline(config), case, extraction) == []
