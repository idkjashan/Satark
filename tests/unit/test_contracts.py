"""Smoke tests for the shared contracts (config, state helpers, registry, fixture DB)."""

import pytest

from satark.checkers.base import BaseChecker, clear, hit, unknown
from satark.checkers.registry import CheckerRegistry, ConfigError
from satark.harness.state import Entity


def test_config_loads(config):
    assert "upi.vpa" in config.entities
    assert config.signals["REG_NAME_MISMATCH"]["weight"] == "critical"
    assert config.scoring["levels"]["HIGH_RISK"]
    assert "check" in config.modes and "chat" in config.modes
    assert config.portals["actions"]["report_1930"]["phone"] == "1930"
    assert any(b["id"] == "sebi" for b in config.brands)


def test_signal_actions_exist(config):
    actions = config.portals["actions"]
    for code, spec in config.signals.items():
        for a in spec.get("actions", []):
            assert a in actions, (code, a)
    for lvl, acts in config.scoring["default_actions"].items():
        for a in acts:
            assert a in actions, (lvl, a)


def test_case_helpers(make_case):
    case = make_case()
    assert case.next_id("e") == "e1" and case.next_id("e") == "e2"
    case.entities.append(Entity(id="e1", type="upi.vpa", cls="C", placeholder="[UPI_1]", norm_hash="h1"))
    assert case.entity("e1").type == "upi.vpa"
    assert case.by_type("upi.vpa") and case.claim("claim.registered_as") is None


def test_fixture_db(fixture_db):
    row = fixture_db.one("SELECT name FROM intermediary WHERE reg_no = ?", ("INH000000002",))
    assert row["name"] == "Rajesh Kumar Sharma"
    assert fixture_db.data_version == 1
    assert fixture_db.source_as_on("sebi_ra") == "2026-10-03"
    fts = fixture_db.query("SELECT rowid FROM intermediary_fts WHERE intermediary_fts MATCH ?", ("rajesh",))
    assert len(fts) == 3


class _Good(BaseChecker):
    id, family = "test.good", "text"
    consumes = frozenset({"message.text"})
    produces = frozenset({"URGENCY"})


class _BadSignal(_Good):
    id = "test.bad"
    produces = frozenset({"NOT_A_CODE"})


class _Leaky(_Good):
    id = "test.leaky"
    consumes = frozenset({"aadhaar"})
    privacy = "public_only"


def test_registry_validation(config):
    reg = CheckerRegistry()
    reg.add(_Good())
    reg.validate(config, env={})
    assert [c.id for c in reg.consumers_of("message.text", "check", {"local"})] == ["test.good"]
    for bad in (_BadSignal(), _Leaky()):
        r = CheckerRegistry()
        r.add(bad)
        with pytest.raises(ConfigError):
            r.validate(config, env={})


def test_result_helpers():
    r = hit("URGENCY", basis="rule", assure="REG_FOUND")
    assert r.status == "hit" and {s.code for s in r.signals} == {"URGENCY", "REG_FOUND"}
    assert clear("REG_FOUND").status == "clear"
    assert unknown("timeout").reason == "timeout"
