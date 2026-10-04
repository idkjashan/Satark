"""Regressions from the real-identifier audit: company names are extracted, an unconfirmed company or app gets a
web search, and the optional Google Safe Browsing check behaves. No network: HTTP is faked."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from satark.checkers.base import CheckContext
from satark.checkers.link import LinkSafeBrowsing
from satark.harness.agent import AgentLoop
from satark.harness.budget import Budget
from satark.harness.extract.pipeline import ExtractorPipeline
from satark.harness.state import CaseState, Entity, utcnow
from satark.harness.tools import Call, ToolRegistry, ToolRun
from satark.infra.http import Offline

NOW = datetime(2026, 10, 3, tzinfo=UTC)


# ---- extraction: a named company becomes a party.name (org) entity, masked ----------------------
@pytest.mark.parametrize("text,name", [
    ("Welcome to Brightcrest Wealthnova Capital Pvt Ltd WhatsApp group", "Brightcrest Wealthnova Capital Pvt Ltd"),
    ("a fake group impersonating 'Lazard Asset Management India', run a scam", "Lazard Asset Management India"),
])
def test_company_name_is_extracted_and_masked(config, make_case, text, name):
    case = make_case()
    ExtractorPipeline(config).regex(case, text, claims=False)  # claims=False: the model is extracting
    party = next(e for e in case.entities if e.type == "party.name")
    assert party.display == name and party.attrs["kind"] == "org"
    assert name not in case.masked_text and party.placeholder in case.masked_text


def test_known_brand_and_bare_suffix_are_not_company_names(config, make_case):
    case = make_case()
    ExtractorPipeline(config).regex(case, "Zerodha Broking Limited and ICICI Securities Limited", claims=False)
    assert not case.by_type("party.name")


# ---- agent loop: an unconfirmed company or app is searched once -----------------------------------
def _run_with(entities, config):
    case = CaseState(case_id="c1", expires_at=utcnow(), masked_text="x", entities=entities)
    run = ToolRun(case=case, mode="check", budget=Budget(verdict_deadline_s=5, run_deadline_s=5, tool_calls=5),
                  emit=lambda t, d: None, on_evidence=lambda ev: None)
    return AgentLoop(None, config, ToolRegistry(config, []), "assess"), run


def _ent(type_, ph, **attrs):
    return Entity(id="e" + ph, type=type_, cls="C", value="v", display="v", placeholder=ph, attrs=attrs)


def test_company_search_forced_for_unfamiliar_org_only_once(config):
    loop, run = _with_org(config)
    call = loop._company_search(run, "web.search", [])
    assert call and "[NAME_1]" in call.args["query"] and "scam" in call.args["query"]
    assert loop._company_search(run, "web.search", [call]) is None  # already chosen this step


def _with_org(config):
    return _run_with([_ent("party.name", "[NAME_1]", kind="org"), _ent("party.name", "[NAME_2]", kind="person")], config)


def test_person_name_is_never_searched(config):
    loop, run = _run_with([_ent("party.name", "[NAME_2]", kind="person")], config)
    assert loop._company_search(run, "web.search", []) is None


# ---- link.safe_browsing ---------------------------------------------------------------------------
class FakeHttp:
    def __init__(self, status=200, body=None, exc=None):
        self.status, self.body, self.exc, self.sent = status, body or {}, exc, None

    async def post_json(self, url, payload, timeout=2.5):  # noqa: ASYNC109
        if self.exc:
            raise self.exc
        self.sent = (url, payload)
        return httpx.Response(self.status, json=self.body)


async def _sb(config, make_case, http, key="k"):
    e = Entity(id="e1", type="url", cls="C", value="https://bad.example/x", display="x")
    c = CheckContext(case=make_case(), config=config, http=http, secrets={"SATARK_SAFE_BROWSING_KEY": key} if key else {}, now=NOW)
    return await LinkSafeBrowsing().check(e, c)


async def test_safe_browsing_hit_clear_and_errors(config, make_case):
    http = FakeHttp(body={"matches": [{"threatType": "SOCIAL_ENGINEERING"}]})
    r = await _sb(config, make_case, http)
    assert r.status == "hit" and {s.code for s in r.signals} == {"URL_KNOWN_PHISHING"}
    assert http.sent[1]["threatInfo"]["threatEntries"] == [{"url": "https://bad.example/x"}]
    assert (await _sb(config, make_case, FakeHttp(body={}))).status == "clear"  # Google answers {} for a clean URL
    assert (await _sb(config, make_case, FakeHttp(status=403))).status == "unknown"  # bad key
    assert (await _sb(config, make_case, FakeHttp(exc=Offline("x")))).reason == "offline"
    assert (await _sb(config, make_case, FakeHttp(), key="")).reason == "source_missing"


def test_safe_browsing_is_disabled_without_its_key_and_enabled_with_it(config):
    from satark.checkers.registry import CheckerRegistry

    off, on = CheckerRegistry(), CheckerRegistry()
    for reg, env in ((off, {}), (on, {"SATARK_SAFE_BROWSING_KEY": "k"})):
        reg.discover()
        reg.validate(config, env=env, db_ok=True)
    assert "link.safe_browsing" in off.disabled and "link.safe_browsing" not in on.disabled


# ---- proof on check_result: honest about what ran --------------------------------------------------
def test_proof_unknown_never_reads_as_pass_and_mismatch_is_a_warning(config, make_case):
    from satark.harness.proof import check_proof
    from satark.harness.state import Evidence, SignalHit, SourceRef

    case = make_case()
    ev = Evidence(id="ev1", step_id="s1", checker_id="link.unshorten", family="link", entity_ids=[], status="unknown",
                  reason="offline")
    p = check_proof(ev, case, config, "en")
    assert p["outcome"] == "unknown" and p["why"] == "Satark is offline" and "Could not" in p["result"]
    ev = Evidence(id="ev2", step_id="s2", checker_id="sebi.reg.name_match", family="registry", entity_ids=[], status="hit",
                  signals=[SignalHit(code="REG_NAME_MISMATCH", basis="registry", entity_ids=[])],
                  facts={"registered_name": "X"}, source=SourceRef(id="sebi_registers", as_on="2026-10-03"))
    p = check_proof(ev, case, config, "en")
    assert p["outcome"] == "warning" and not p["result"].startswith("Found:") and p["url"]
