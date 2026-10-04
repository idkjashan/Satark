"""Unit tests for satark/checkers/social.py against the fixture DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import SecretStr

from satark.checkers.base import CheckContext
from satark.checkers.social import SocialOfficialHandles
from satark.harness.state import CaseState, Entity, utcnow
from tests.fixtures.fixture_db import SCHEMA


def _entity(id_: str, type_: str, value: str, cls: str = "C", **kw) -> Entity:
    return Entity(id=id_, type=type_, cls=cls, value=SecretStr(value), display=value, **kw)


def _case(*entities: Entity) -> CaseState:
    case = CaseState(case_id="t", expires_at=utcnow())
    case.entities.extend(entities)
    return case


def _ctx(case: CaseState, config, db=None) -> CheckContext:
    return CheckContext(case=case, config=config, db=db)


def _empty_db(tmp_path: Path):
    from satark.infra.db import RegistryDB

    path = tmp_path / "empty.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    con.execute("INSERT INTO meta VALUES ('data_version', '1')")
    con.commit()
    con.close()
    return RegistryDB(path)


async def test_official_handle_exact_match(config, fixture_db):
    e = _entity("e1", "social.handle", "x:zerodhaonline")
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and [s.code for s in res.signals] == ["HANDLE_OFFICIAL"]
    assert res.facts["entity_name"] == "ZERODHA BROKING LIMITED"


async def test_official_handle_tg_link_exact_match(config, fixture_db):
    e = _entity("e1", "tg.link", "t.me/groww_official")
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and [s.code for s in res.signals] == ["HANDLE_OFFICIAL"]


async def test_handle_lookalike_via_db_fuzzy(config, fixture_db):
    e = _entity("e1", "social.handle", "x:zerodha_online")  # vs official "zerodhaonline", ratio ~96%
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["HANDLE_LOOKALIKE_OFFICIAL"]
    assert res.facts["looks_like"] == "zerodhaonline"


async def test_handle_lookalike_via_brand_alias(config, fixture_db):
    # no official "instagram" handles in the fixture DB at all; caught by the brands.yaml alias instead
    e = _entity("e1", "social.handle", "instagram:groww_support_team")
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["HANDLE_LOOKALIKE_OFFICIAL"]
    assert res.facts["looks_like"] == "groww"


async def test_handle_unrelated_is_clear(config, fixture_db):
    e = _entity("e1", "social.handle", "linkedin:totally_unrelated_handle999")
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_handle_source_missing(config, tmp_path):
    e = _entity("e1", "social.handle", "x:zerodhaonline")
    res = await SocialOfficialHandles().check(e, _ctx(_case(e), config, db=_empty_db(tmp_path)))
    assert res.status == "unknown" and res.reason == "source_missing"
