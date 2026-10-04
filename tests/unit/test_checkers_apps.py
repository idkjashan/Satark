"""Unit tests for satark/checkers/apps.py. HTTP is always faked; never touches the network."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from satark.checkers.apps import AppBrokerRegistry, AppPlayListing, AppRemoteAccess
from satark.checkers.base import CheckContext, TransientError
from satark.harness.state import CaseState, Entity, utcnow
from tests.fixtures.fixture_db import SCHEMA

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http"


def _entity(id_: str, type_: str, value: str, cls: str = "C", **kw) -> Entity:
    return Entity(id=id_, type=type_, cls=cls, value=SecretStr(value), display=value, **kw)


def _case(*entities: Entity) -> CaseState:
    case = CaseState(case_id="t", expires_at=utcnow())
    case.entities.extend(entities)
    return case


def _ctx(case: CaseState, config, db=None, http=None) -> CheckContext:
    return CheckContext(case=case, config=config, db=db, http=http)


def _empty_db(tmp_path: Path):
    from satark.infra.db import RegistryDB

    path = tmp_path / "empty.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    con.execute("INSERT INTO meta VALUES ('data_version', '1')")
    con.commit()
    con.close()
    return RegistryDB(path)


class _FakeHttp:
    """Stand-in for satark.infra.http.SafeHttpClient: same async get(url, timeout=...) -> httpx.Response shape."""

    def __init__(self, status: int = 200, text: str = "", exc: Exception | None = None):
        self.status, self.text, self.exc = status, text, exc

    async def get(self, url: str, timeout: float = 5.0, headers=None, max_bytes: int = 512_000):  # noqa: ASYNC109 -- mirrors SafeHttpClient.get
        if self.exc:
            raise self.exc
        return httpx.Response(self.status, text=self.text, request=httpx.Request("GET", url))


class Offline(Exception):
    """Stands in for satark.infra.http.Offline; apps.py matches exceptions by class name."""


# ======================================================================== app.play_listing


async def test_play_listing_broker_app_matches_developer(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    imp = _entity("e2", "claim.impersonates", "", cls="P", attrs={"kind": "broker", "org": "Zerodha"})
    http = _FakeHttp(200, (FIXTURES / "play_kite.html").read_text(encoding="utf-8"))
    res = await AppPlayListing().check(e, _ctx(_case(e, imp), config, http=http))
    assert res.status == "clear"
    assert "APP_SEBI_VERIFIED" in [s.code for s in res.signals]
    assert res.facts["developer"] == "Zerodha"
    assert res.facts["title"] == "Zerodha Kite - Trade & Invest"


async def test_play_listing_developer_mismatch(config):
    e = _entity("e1", "app.package", "com.whatsapp")
    imp = _entity("e2", "claim.impersonates", "", cls="P", attrs={"kind": "broker", "org": "Zerodha"})
    http = _FakeHttp(200, (FIXTURES / "play_other.html").read_text(encoding="utf-8"))
    res = await AppPlayListing().check(e, _ctx(_case(e, imp), config, http=http))
    assert res.status == "hit" and "APP_DEVELOPER_MISMATCH" in [s.code for s in res.signals]
    assert res.facts["developer"] == "WhatsApp LLC"
    assert "APP_SEBI_VERIFIED" not in [s.code for s in res.signals]


async def test_play_listing_404_hits_with_trading_context(config):
    e = _entity("e1", "app.package", "com.totally.fake")
    text = _entity("e2", "message.text", "Install our trading app now")
    http = _FakeHttp(404)
    res = await AppPlayListing().check(e, _ctx(_case(e, text), config, http=http))
    assert res.status == "hit" and [s.code for s in res.signals] == ["APP_NOT_ON_PLAY"]


async def test_play_listing_404_hits_even_without_any_context(config):
    # product decision: a dead Play link is suspicious in any message, no keyword-context gate.
    e = _entity("e1", "app.package", "com.totally.fake")
    http = _FakeHttp(404)
    res = await AppPlayListing().check(e, _ctx(_case(e), config, http=http))
    assert res.status == "hit" and [s.code for s in res.signals] == ["APP_NOT_ON_PLAY"]


async def test_play_listing_developer_mismatch_requires_impersonation_claim(config):
    # unlisted-but-present developer name with NO claim.impersonates at all: no mismatch signal.
    e = _entity("e1", "app.package", "com.whatsapp")
    http = _FakeHttp(200, (FIXTURES / "play_other.html").read_text(encoding="utf-8"))
    res = await AppPlayListing().check(e, _ctx(_case(e), config, http=http))
    assert res.status == "clear" and not res.signals


async def test_play_listing_developer_mismatch_amc_kind(config):
    e = _entity("e1", "app.package", "com.whatsapp")
    imp = _entity("e2", "claim.impersonates", "", cls="P", attrs={"kind": "amc", "org": "Zerodha"})
    http = _FakeHttp(200, (FIXTURES / "play_other.html").read_text(encoding="utf-8"))
    res = await AppPlayListing().check(e, _ctx(_case(e, imp), config, http=http))
    assert res.status == "hit" and "APP_DEVELOPER_MISMATCH" in [s.code for s in res.signals]


async def test_play_listing_offline(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    res = await AppPlayListing().check(e, _ctx(_case(e), config, http=_FakeHttp(exc=Offline())))
    assert res.status == "unknown" and res.reason == "offline"


async def test_play_listing_503_is_transient(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    http = _FakeHttp(503)
    with pytest.raises(TransientError):
        await AppPlayListing().check(e, _ctx(_case(e), config, http=http))


async def test_play_listing_connection_error_is_transient(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    http = _FakeHttp(exc=httpx.ConnectError("boom"))
    with pytest.raises(TransientError):
        await AppPlayListing().check(e, _ctx(_case(e), config, http=http))


async def test_play_listing_malformed_html_is_unknown(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    http = _FakeHttp(200, "<<<not really html>>>")
    res = await AppPlayListing().check(e, _ctx(_case(e), config, http=http))
    assert res.status == "unknown" and res.reason == "unparseable"


# ======================================================================== app.broker_registry


async def test_broker_registry_listed(config, fixture_db):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    res = await AppBrokerRegistry().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and [s.code for s in res.signals] == ["APP_IN_BROKER_REGISTRY"]
    assert res.facts["member_name"] == "ZERODHA BROKING LIMITED"


async def test_broker_registry_claims_broker_not_listed(config, fixture_db):
    e = _entity("e1", "app.package", "com.totally.fake")
    imp = _entity("e2", "claim.impersonates", "", cls="P", attrs={"kind": "broker", "org": "Zerodha"})
    res = await AppBrokerRegistry().check(e, _ctx(_case(e, imp), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["APP_CLAIMS_BROKER_NOT_LISTED"]


async def test_broker_registry_claims_via_registered_as_category(config, fixture_db):
    e = _entity("e1", "app.package", "com.totally.fake")
    claim = _entity("e2", "claim.registered_as", "", cls="P", attrs={"category": "BROKER"})
    res = await AppBrokerRegistry().check(e, _ctx(_case(e, claim), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["APP_CLAIMS_BROKER_NOT_LISTED"]


async def test_broker_registry_unlisted_no_claim_is_clear(config, fixture_db):
    e = _entity("e1", "app.package", "com.totally.fake")
    res = await AppBrokerRegistry().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_broker_registry_unlisted_keyword_alone_is_clear(config, fixture_db):
    # product decision: message wording alone must not gate this signal, only claims/facts.
    e = _entity("e1", "app.package", "com.totally.fake")
    text = _entity("e2", "message.text", "Install this trading app to start investing in stocks")
    res = await AppBrokerRegistry().check(e, _ctx(_case(e, text), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_broker_registry_source_missing(config, tmp_path):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    res = await AppBrokerRegistry().check(e, _ctx(_case(e), config, db=_empty_db(tmp_path)))
    assert res.status == "unknown" and res.reason == "source_missing"


# ======================================================================== app.remote_access


async def test_remote_access_known_package(config):
    e = _entity("e1", "app.package", "com.anydesk.anydeskandroid")
    res = await AppRemoteAccess().check(e, _ctx(_case(e), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REMOTE_ACCESS_REQUEST"]


async def test_remote_access_unrelated_package_is_clear(config):
    e = _entity("e1", "app.package", "com.zerodha.kite3")
    res = await AppRemoteAccess().check(e, _ctx(_case(e), config))
    assert res.status == "clear" and not res.signals


async def test_remote_access_claim(config):
    e = _entity("e1", "request.remote_access", "", cls="P")
    res = await AppRemoteAccess().check(e, _ctx(_case(e), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["REMOTE_ACCESS_REQUEST"]


async def test_remote_access_claim_llm_basis(config):
    e = _entity("e1", "request.remote_access", "", cls="P", origin="llm")
    res = await AppRemoteAccess().check(e, _ctx(_case(e), config))
    assert res.signals[0].basis == "llm_claim"
