"""Tests for the link checker family (satark/checkers/link.py)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from satark.checkers.base import CheckContext, TransientError
from satark.checkers.link import (
    LinkApk,
    LinkBlocklist,
    LinkDomainRules,
    LinkGoogleHosted,
    LinkLookalike,
    LinkOfficial,
    LinkPopularity,
    LinkRdapAge,
    LinkUnshorten,
)
from satark.harness.state import Entity
from satark.infra.db import RegistryDB
from satark.infra.http import BlockedURL, Offline

NOW = datetime(2026, 10, 3, tzinfo=UTC)
SCHEMA = Path(__file__).resolve().parents[2] / "satark" / "ingest" / "schema.sql"
SBI_RDAP_FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "tests/fixtures/http/rdap_sbi_bank_in.json").read_text()
)


@pytest.fixture
def empty_db(tmp_path):
    """A registry DB with the real schema but zero rows anywhere (an unseeded source)."""
    path = tmp_path / "empty.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    con.commit()
    con.close()
    db = RegistryDB(path)
    yield db
    db.close()


def ctx(config, db=None, http=None, case=None, make_case=None):
    return CheckContext(case=case or make_case(), config=config, db=db, http=http, now=NOW)


def entity(type_: str, value: str = "", cls: str = "C", **attrs) -> Entity:
    return Entity(id="e1", type=type_, cls=cls, value=value, display=value, attrs=attrs)


class FakeHttp:
    network = True

    def __init__(self, redirects=None, response=None, exc=None):
        self.redirects = redirects
        self.response = response
        self.exc = exc

    async def resolve_redirects(self, url, max_hops=3, timeout=1.5):  # noqa: ASYNC109
        if self.exc:
            raise self.exc
        return self.redirects

    async def get(self, url, timeout=2.5, headers=None, max_bytes=512_000):  # noqa: ASYNC109
        if self.exc:
            raise self.exc
        return self.response


# ---- link.unshorten -----------------------------------------------------------------------


async def test_unshorten_follows_chain_and_derives_apk(config, make_case):
    checker = LinkUnshorten()
    http = FakeHttp(redirects=["https://bit.ly/x", "https://scam-app.xyz/app.apk"])
    e = entity("url", "https://bit.ly/x")
    result = await checker.check(e, ctx(config, http=http, make_case=make_case))
    assert result.status == "hit"
    assert {s.code for s in result.signals} == {"URL_SHORTENED"}
    assert result.facts["hops"] == 1
    derived_types = {d.type for d in result.derived}
    assert derived_types == {"url", "apk.link"}


async def test_unshorten_offline_and_blocked(config, make_case):
    checker = LinkUnshorten()
    e = entity("url", "https://bit.ly/x")
    r1 = await checker.check(e, ctx(config, http=FakeHttp(exc=Offline("x")), make_case=make_case))
    assert r1.status == "unknown" and r1.reason == "offline"
    r2 = await checker.check(e, ctx(config, http=FakeHttp(exc=BlockedURL("x")), make_case=make_case))
    assert r2.status == "unknown" and r2.reason == "blocked"


async def test_unshorten_connection_error_is_transient(config, make_case):
    checker = LinkUnshorten()
    e = entity("url", "https://bit.ly/x")
    with pytest.raises(TransientError):
        await checker.check(e, ctx(config, http=FakeHttp(exc=httpx.ConnectError("boom")), make_case=make_case))


async def test_unshorten_runs_on_every_url_not_just_known_shorteners(config, make_case):
    """No allow-list gate: a non-shortener host that still redirects cross-domain must be caught."""
    checker = LinkUnshorten()
    http = FakeHttp(redirects=["https://zerodha-support.in/go", "https://scam-app.xyz/login"])
    e = entity("url", "https://zerodha-support.in/go")
    result = await checker.check(e, ctx(config, http=http, make_case=make_case))
    assert result.status == "hit" and {s.code for s in result.signals} == {"URL_SHORTENED"}
    assert result.facts["final_domain_raw"] == "scam-app.xyz"


async def test_unshorten_same_domain_redirect_is_clear_but_still_derives(config, make_case):
    """A redirect that stays on the same domain is not itself suspicious, but the final url
    (e.g. a path ending in .apk) is still worth deriving."""
    checker = LinkUnshorten()
    http = FakeHttp(redirects=["https://zerodha.com/go", "https://zerodha.com/final"])
    e = entity("url", "https://zerodha.com/go")
    result = await checker.check(e, ctx(config, http=http, make_case=make_case))
    assert result.status == "clear" and not result.signals
    assert {d.type for d in result.derived} == {"url"}


async def test_unshorten_no_redirect_non_shortener_is_clear(config, make_case):
    checker = LinkUnshorten()
    http = FakeHttp(redirects=["https://zerodha.com/kite"])
    e = entity("url", "https://zerodha.com/kite")
    result = await checker.check(e, ctx(config, http=http, make_case=make_case))
    assert result.status == "clear" and not result.signals and not result.derived


# ---- link.blocklist -----------------------------------------------------------------------


async def test_blocklist_hit(config, fixture_db, make_case):
    checker = LinkBlocklist()
    e = entity("domain", "phish-example.xyz")
    result = await checker.check(e, ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "hit"
    assert {s.code for s in result.signals} == {"URL_KNOWN_PHISHING"}
    assert result.source.id == "blocklists"


async def test_blocklist_clear(config, fixture_db, make_case):
    checker = LinkBlocklist()
    e = entity("domain", "zerodha.com")
    result = await checker.check(e, ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and not result.signals


async def test_blocklist_source_missing(config, empty_db, make_case):
    checker = LinkBlocklist()
    e = entity("domain", "phish-example.xyz")
    result = await checker.check(e, ctx(config, db=empty_db, make_case=make_case))
    assert result.status == "unknown" and result.reason == "source_missing"


# ---- link.rdap_age ------------------------------------------------------------------------


def _rdap_response(reg_date: str, status: int = 200) -> httpx.Response:
    data = {"events": [{"eventAction": "registration", "eventDate": reg_date}]}
    return httpx.Response(status, json=data)


async def test_rdap_age_real_fixture_sbi_bank_in(config, make_case):
    checker = LinkRdapAge()
    http = FakeHttp(response=httpx.Response(200, json=SBI_RDAP_FIXTURE))
    e = entity("domain", "sbi.bank.in")
    result = await checker.check(e, ctx(config, http=http, make_case=make_case))
    assert result.status == "clear" and not result.signals  # ~14 months old: neither young nor old
    assert result.facts["registered_on"] == "2025-08-11T09:44:16.203Z"
    assert 300 < result.facts["age_days"] < 500


async def test_rdap_age_young_domain(config, make_case):
    checker = LinkRdapAge()
    http = FakeHttp(response=_rdap_response("2026-09-20T00:00:00Z"))
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, http=http, make_case=make_case))
    assert result.status == "hit" and {s.code for s in result.signals} == {"DOMAIN_YOUNG"}
    assert result.facts["age_days"] < 90


async def test_rdap_age_old_domain(config, make_case):
    checker = LinkRdapAge()
    http = FakeHttp(response=_rdap_response("2015-01-01T00:00:00Z"))
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, http=http, make_case=make_case))
    assert result.status == "clear" and {s.code for s in result.signals} == {"DOMAIN_OLD"}


async def test_rdap_age_not_found(config, make_case):
    checker = LinkRdapAge()
    http = FakeHttp(response=httpx.Response(404))
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, http=http, make_case=make_case))
    assert result.status == "clear" and result.facts.get("rdap_not_found") is True


async def test_rdap_age_server_error_is_transient(config, make_case):
    checker = LinkRdapAge()
    http = FakeHttp(response=httpx.Response(503))
    with pytest.raises(TransientError):
        await checker.check(entity("domain", "zerodha.com"), ctx(config, http=http, make_case=make_case))


async def test_rdap_age_offline_and_blocked(config, make_case):
    checker = LinkRdapAge()
    e = entity("domain", "zerodha.com")
    r1 = await checker.check(e, ctx(config, http=FakeHttp(exc=Offline("x")), make_case=make_case))
    assert r1.status == "unknown" and r1.reason == "offline"
    r2 = await checker.check(e, ctx(config, http=FakeHttp(exc=BlockedURL("x")), make_case=make_case))
    assert r2.status == "unknown" and r2.reason == "blocked"


async def test_rdap_age_no_bootstrap_entry(config, make_case):
    checker = LinkRdapAge()
    e = entity("domain", "example.qqzz")
    result = await checker.check(e, ctx(config, http=FakeHttp(), make_case=make_case))
    assert result.status == "unknown" and result.reason == "source_missing"


# ---- link.lookalike -----------------------------------------------------------------------


async def test_lookalike_exact_official_is_clear(config, fixture_db, make_case):
    checker = LinkLookalike()
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and not result.signals


@pytest.mark.parametrize(
    "domain,looks_like",
    [
        ("zer0dha.com", "zerodha.com"),  # confusable skeleton (0 -> o)
        ("zerodhaa.com", "zerodha.com"),  # rapidfuzz near-miss
        ("zerodha-support.in", "zerodha.com"),  # brand token
        ("sebi-refund.com", "sebi.gov.in"),  # brand token (task example)
        ("groww-vip.app", "groww.in"),  # brand token (task example)
    ],
)
async def test_lookalike_hits(config, fixture_db, make_case, domain, looks_like):
    checker = LinkLookalike()
    result = await checker.check(entity("domain", domain), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "hit"
    assert {s.code for s in result.signals} == {"DOMAIN_LOOKALIKE"}
    assert result.facts["looks_like_raw"] == looks_like


async def test_lookalike_unrelated_domain_is_clear(config, fixture_db, make_case):
    checker = LinkLookalike()
    result = await checker.check(entity("domain", "example.org"), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and not result.signals


async def test_lookalike_source_missing(config, empty_db, make_case):
    checker = LinkLookalike()
    result = await checker.check(entity("domain", "zer0dha.com"), ctx(config, db=empty_db, make_case=make_case))
    assert result.status == "unknown" and result.reason == "source_missing"


# ---- link.official ------------------------------------------------------------------------


async def test_official_hit(config, fixture_db, make_case):
    checker = LinkOfficial()
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and {s.code for s in result.signals} == {"DOMAIN_OFFICIAL"}
    assert result.facts["entity_name"] == "Zerodha"


async def test_official_not_found(config, fixture_db, make_case):
    checker = LinkOfficial()
    result = await checker.check(entity("domain", "example.org"), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and not result.signals


async def test_official_source_missing(config, empty_db, make_case):
    checker = LinkOfficial()
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, db=empty_db, make_case=make_case))
    assert result.status == "unknown" and result.reason == "source_missing"


# ---- link.domain_rules --------------------------------------------------------------------


def _impersonates(**attrs) -> Entity:
    return Entity(id="c1", type="claim.impersonates", cls="P", attrs=attrs)


async def test_domain_rules_bank_not_bank_in(config, fixture_db, make_case):
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="bank", brand_id="sbi", org="State Bank of India"))
    result = await checker.check(entity("domain", "sbi-online.xyz"), ctx(config, db=fixture_db, case=case))
    assert {s.code for s in result.signals} == {"BANK_NOT_BANK_IN"}


async def test_domain_rules_bank_on_bank_in_is_clear(config, fixture_db, make_case):
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="bank", brand_id="sbi"))
    result = await checker.check(entity("domain", "sbi.bank.in"), ctx(config, db=fixture_db, case=case))
    assert result.status == "clear" and not result.signals


async def test_domain_rules_bank_official_but_not_bank_in_is_clear(config, fixture_db, make_case):
    """HDFC Bank's genuine domain is hdfcbank.com, not *.bank.in: the official guard must excuse it."""
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="bank", brand_id="hdfcbank"))
    result = await checker.check(entity("domain", "hdfcbank.com"), ctx(config, db=fixture_db, case=case))
    assert result.status == "clear" and not result.signals


async def test_domain_rules_govt_not_gov_in(config, fixture_db, make_case):
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="regulator", brand_id="sebi"))
    result = await checker.check(entity("domain", "sebi-helpdesk.net"), ctx(config, db=fixture_db, case=case))
    assert {s.code for s in result.signals} == {"GOVT_NOT_GOV_IN"}


async def test_domain_rules_govt_on_gov_in_is_clear(config, fixture_db, make_case):
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="regulator", brand_id="sebi"))
    result = await checker.check(entity("domain", "sebi.gov.in"), ctx(config, db=fixture_db, case=case))
    assert result.status == "clear" and not result.signals


async def test_domain_rules_known_spoof(config, fixture_db, make_case):
    checker = LinkDomainRules()
    result = await checker.check(entity("domain", "iepf.org.in"), ctx(config, db=fixture_db, make_case=make_case))
    assert {s.code for s in result.signals} == {"OFFICIAL_DOMAIN_SPOOF"}


async def test_domain_rules_email_spoof_of_sebi(config, fixture_db, make_case):
    checker = LinkDomainRules()
    case = make_case()
    case.entities.append(_impersonates(kind="regulator", brand_id="sebi"))
    case.entities.append(entity("email", "officer@sebi-notice.com"))
    result = await checker.check(entity("domain", "sebi-notice.com"), ctx(config, db=fixture_db, case=case))
    assert "OFFICIAL_DOMAIN_SPOOF" in {s.code for s in result.signals}


async def test_domain_rules_no_claim_is_clear(config, fixture_db, make_case):
    checker = LinkDomainRules()
    result = await checker.check(entity("domain", "example.org"), ctx(config, db=fixture_db, make_case=make_case))
    assert result.status == "clear" and not result.signals


# ---- link.apk -----------------------------------------------------------------------------


async def test_apk_always_hits(config, make_case):
    checker = LinkApk()
    result = await checker.check(entity("apk.link", "https://scam.xyz/app.apk"), ctx(config, make_case=make_case))
    assert result.status == "hit" and {s.code for s in result.signals} == {"SIDELOAD_APK"}


# ---- link.google_hosted -------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://forms.gle/abc123",
        "https://docs.google.com/forms/d/e/xyz/viewform",
        "https://scam.netlify.app/login",
        "https://scam.web.app/",
    ],
)
async def test_google_hosted_hits(config, make_case, url):
    checker = LinkGoogleHosted()
    result = await checker.check(entity("url", url), ctx(config, make_case=make_case))
    assert result.status == "hit" and {s.code for s in result.signals} == {"FREE_HOSTED_LANDING"}


@pytest.mark.parametrize("url", ["https://docs.google.com/document/d/xyz", "https://zerodha.com/app"])
async def test_google_hosted_clear(config, make_case, url):
    checker = LinkGoogleHosted()
    result = await checker.check(entity("url", url), ctx(config, make_case=make_case))
    assert result.status == "clear" and not result.signals


# ---- link.popularity ----------------------------------------------------------------------


def test_popularity_should_run_requires_impersonation(make_case):
    checker = LinkPopularity()
    case = make_case()
    assert checker.should_run(entity("domain", "zerodha.com"), case) is False
    case.entities.append(_impersonates(kind="broker", brand_id="zerodha"))
    assert checker.should_run(entity("domain", "zerodha.com"), case) is True


async def test_popularity_popular_domain_is_clear(config, fixture_db, make_case):
    checker = LinkPopularity()
    case = make_case()
    case.entities.append(_impersonates(kind="broker", brand_id="zerodha"))
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, db=fixture_db, case=case))
    assert result.status == "clear" and not result.signals


async def test_popularity_unpopular_domain_hits(config, fixture_db, make_case):
    checker = LinkPopularity()
    case = make_case()
    case.entities.append(_impersonates(kind="broker", brand_id="zerodha"))
    result = await checker.check(entity("domain", "zerodha-support.in"), ctx(config, db=fixture_db, case=case))
    assert {s.code for s in result.signals} == {"DOMAIN_UNPOPULAR_FOR_BRAND"}


async def test_popularity_official_but_unpopular_is_clear(config, fixture_db, make_case):
    """rbi.org.in is official but isn't in the (tiny) fixture popularity table: official excuses it."""
    checker = LinkPopularity()
    case = make_case()
    case.entities.append(_impersonates(kind="regulator", brand_id="rbi"))
    result = await checker.check(entity("domain", "rbi.org.in"), ctx(config, db=fixture_db, case=case))
    assert result.status == "clear" and not result.signals


async def test_popularity_source_missing(config, empty_db, make_case):
    checker = LinkPopularity()
    case = make_case()
    case.entities.append(_impersonates(kind="broker", brand_id="zerodha"))
    result = await checker.check(entity("domain", "zerodha.com"), ctx(config, db=empty_db, case=case))
    assert result.status == "unknown" and result.reason == "source_missing"
