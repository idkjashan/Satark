"""Unit tests for satark/checkers/sebi.py against the fixture DB (tests/fixtures/fixture_db.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import SecretStr

from satark.checkers.base import CheckContext
from satark.checkers.sebi import (
    CautionMatch,
    SebiDebarred,
    SebiRegFormat,
    SebiRegistrySearch,
    SebiRegLookup,
    SebiRegNameMatch,
)
from satark.harness.state import CaseState, Entity, utcnow
from tests.fixtures.fixture_db import SCHEMA

# ---- small local helpers (duplicated per test file on purpose: each file is independently owned) ----


def _entity(id_: str, type_: str, value: str, cls: str = "C", **kw) -> Entity:
    return Entity(id=id_, type=type_, cls=cls, value=SecretStr(value), display=value, **kw)


def _case(*entities: Entity) -> CaseState:
    case = CaseState(case_id="t", expires_at=utcnow())
    case.entities.extend(entities)
    return case


def _ctx(case: CaseState, config, db=None) -> CheckContext:
    return CheckContext(case=case, config=config, db=db)


def _empty_db(tmp_path: Path):
    """A RegistryDB with the real schema but every table empty (for source_missing tests)."""
    from satark.infra.db import RegistryDB

    path = tmp_path / "empty.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    con.execute("INSERT INTO meta VALUES ('data_version', '1')")
    con.commit()
    con.close()
    return RegistryDB(path)


# ======================================================================== sebi.reg.format


async def test_reg_format_valid_formats(config):
    checker = SebiRegFormat()
    for value in ("INH000000002", "INA000000001", "IN-DP-192-2016", "MF/020/94/8", "IN/AIF1/17-18/0312"):
        e = _entity("e1", "sebi.reg_no", value)
        res = await checker.check(e, _ctx(_case(e), config))
        assert res.status == "clear" and not res.signals, value


async def test_reg_format_invalid(config):
    checker = SebiRegFormat()
    e = _entity("e1", "sebi.reg_no", "INH12")
    res = await checker.check(e, _ctx(_case(e), config))
    assert res.status == "hit"
    assert [s.code for s in res.signals] == ["REG_FORMAT_INVALID"]
    assert res.signals[0].basis == "rule"


async def test_reg_format_llm_basis(config):
    e = _entity("e1", "sebi.reg_no", "BAD", origin="llm")
    res = await SebiRegFormat().check(e, _ctx(_case(e), config))
    assert res.signals[0].basis == "llm_claim"


# ======================================================================== sebi.reg.lookup


async def test_reg_lookup_found(config, fixture_db):
    e = _entity("e1", "sebi.reg_no", "INA000000001")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear"
    assert [s.code for s in res.signals] == ["REG_FOUND"]
    assert res.facts["registered_name"] == "Test Advisors Private Limited"
    assert res.facts["category"] == "IA"
    assert res.source.id == "sebi_registers"


async def test_reg_lookup_expired(config, fixture_db):
    e = _entity("e1", "sebi.reg_no", "INA000000004")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"
    assert [s.code for s in res.signals] == ["REG_EXPIRED"]
    assert res.facts["valid_to"] == "2020-01-01"


async def test_reg_lookup_not_found(config, fixture_db):
    e = _entity("e1", "sebi.reg_no", "INZ000000999")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REG_NOT_FOUND"]


async def test_reg_lookup_bad_format_defers_to_format_checker(config, fixture_db):
    e = _entity("e1", "sebi.reg_no", "NOTAREGNO")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_reg_lookup_source_missing_no_db(config):
    e = _entity("e1", "sebi.reg_no", "INA000000001")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, db=None))
    assert res.status == "unknown" and res.reason == "source_missing"


async def test_reg_lookup_source_missing_empty_table(config, tmp_path):
    e = _entity("e1", "sebi.reg_no", "INA000000001")
    res = await SebiRegLookup().check(e, _ctx(_case(e), config, db=_empty_db(tmp_path)))
    assert res.status == "unknown" and res.reason == "source_missing"


# ======================================================================== sebi.reg.name_match


def _claim_case(name_value: str, reg_value: str, category: str | None = None):
    name_e = _entity("e1", "party.name", name_value)
    reg_e = _entity("e2", "sebi.reg_no", reg_value)
    attrs = {"regulator": "SEBI"}
    if category:
        attrs["category"] = category
    claim_e = _entity("e3", "claim.registered_as", "", cls="P", attrs=attrs, refs=["e1", "e2"])
    return claim_e, _case(name_e, reg_e, claim_e)


async def test_name_match_exact(config, fixture_db):
    claim, case = _claim_case("Rajesh Kumar Sharma", "INH000000002", category="RA")
    res = await SebiRegNameMatch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "clear" and [s.code for s in res.signals] == ["REG_FOUND"]


async def test_name_match_mismatch(config, fixture_db):
    claim, case = _claim_case("Suresh Mehta Advisory", "INH000000002")
    res = await SebiRegNameMatch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REG_NAME_MISMATCH"]
    assert res.facts["claimed_name_raw"] == "Suresh Mehta Advisory"


async def test_name_match_ambiguous(config, fixture_db):
    claim, case = _claim_case("Rajesh Sharma Wealth", "INH000000002")
    res = await SebiRegNameMatch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "clear" and "AMBIGUOUS_MATCH" in res.flags
    assert res.facts["candidates"]


async def test_name_match_category_mismatch(config, fixture_db):
    claim, case = _claim_case("Rajesh Kumar Sharma", "INH000000002", category="IA")
    res = await SebiRegNameMatch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REG_CATEGORY_MISMATCH"]


async def test_name_match_no_refs_clears(config, fixture_db):
    claim = _entity("e1", "claim.registered_as", "", cls="P")
    res = await SebiRegNameMatch().check(claim, _ctx(_case(claim), config, fixture_db))
    assert res.status == "clear" and not res.signals
    assert SebiRegNameMatch().should_run(claim, _case(claim)) is False


# ======================================================================== sebi.registry.search


def _search_case(name_value: str):
    name_e = _entity("e1", "party.name", name_value)
    claim_e = _entity("e2", "claim.registered_as", "", cls="P", refs=["e1"])
    return claim_e, _case(name_e, claim_e)


async def test_registry_search_found(config, fixture_db):
    claim, case = _search_case("Rajesh Kumar Sharma")
    res = await SebiRegistrySearch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "clear" and [s.code for s in res.signals] == ["REG_FOUND"]
    assert res.facts["reg_no"] == "INH000000002"


async def test_registry_search_ambiguous(config, fixture_db):
    claim, case = _search_case("Rajesh Sharma Wealth")
    res = await SebiRegistrySearch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "clear" and "AMBIGUOUS_MATCH" in res.flags
    assert len(res.facts["candidates"]) <= 3


async def test_registry_search_not_found(config, fixture_db):
    claim, case = _search_case("Totally Unknown Entity Xyz")
    res = await SebiRegistrySearch().check(claim, _ctx(case, config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REG_CLAIM_NOT_FOUND"]


async def test_registry_search_skips_when_reg_no_present(config, fixture_db):
    claim, case = _claim_case("Rajesh Kumar Sharma", "INH000000002")
    assert SebiRegistrySearch().should_run(claim, case) is False


# ======================================================================== sebi.debarred


async def test_debarred_by_pan(config, fixture_db):
    e = _entity("e1", "pan", "ABCPF1234K")
    res = await SebiDebarred().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["DEBARRED_ENTITY"]
    assert res.facts["order_ref"] == "NSE/INVG/00001"


async def test_debarred_by_name(config, fixture_db):
    e = _entity("e1", "party.name", "Pump Masters Private Limited")
    res = await SebiDebarred().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["DEBARRED_ENTITY"]


async def test_debarred_short_name_never_matches(config, fixture_db):
    e = _entity("e1", "party.name", "Raj")  # too short/few tokens: must not even query
    res = await SebiDebarred().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_debarred_clean_name(config, fixture_db):
    e = _entity("e1", "party.name", "Totally Fine Advisors")
    res = await SebiDebarred().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_debarred_source_missing(config, tmp_path):
    e = _entity("e1", "pan", "ABCPF1234K")
    res = await SebiDebarred().check(e, _ctx(_case(e), config, db=_empty_db(tmp_path)))
    assert res.status == "unknown" and res.reason == "source_missing"


# ======================================================================== caution.match


async def test_caution_match_name(config, fixture_db):
    e = _entity("e1", "party.name", "Quick Profit Advisory")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["ON_CAUTION_LIST"]
    assert res.facts["list_id"] == "nse_caution"


async def test_caution_match_phone(config, fixture_db):
    e = _entity("e1", "phone", "+919999900000")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"


async def test_caution_match_domain(config, fixture_db):
    e = _entity("e1", "domain", "fake-sebi-refund.in")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"


async def test_caution_match_url_uses_registrable_domain(config, fixture_db):
    e = _entity("e1", "url", "https://sub.fake-sebi-refund.in/claim?x=1")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"


async def test_caution_match_upi(config, fixture_db):
    e = _entity("e1", "upi.vpa", "scammer@ybl")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"


async def test_caution_match_telegram(config, fixture_db):
    e = _entity("e1", "tg.link", "t.me/bullrun_vip")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit"


async def test_caution_match_negative(config, fixture_db):
    e = _entity("e1", "party.name", "Totally Fine Advisors")
    res = await CautionMatch().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_caution_match_source_missing(config, tmp_path):
    e = _entity("e1", "party.name", "Quick Profit Advisory")
    res = await CautionMatch().check(e, _ctx(_case(e), config, db=_empty_db(tmp_path)))
    assert res.status == "unknown" and res.reason == "source_missing"
