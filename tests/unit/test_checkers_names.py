"""names.scan: official-list names found anywhere in the message, firms only."""

from pydantic import SecretStr

from satark.checkers.base import CheckContext
from satark.checkers.names import NamesScan
from satark.harness.state import Entity
from satark.infra.norm import looks_like_org


def _ctx(case, config, db):
    return CheckContext(case=case, config=config, db=db)


def _msg(text: str) -> Entity:
    return Entity(id="e1", type="message.text", cls="C", value=SecretStr(text))


async def test_debarred_firm_in_text_is_found(make_case, config, fixture_db):
    r = await NamesScan().check(_msg("Join Pump Masters Private Limited for multibagger calls"), _ctx(make_case(), config, fixture_db))
    assert r.status == "hit" and [s.code for s in r.signals] == ["DEBARRED_ENTITY"]
    assert r.facts["debarred"][0]["order_ref"] == "NSE/INVG/00002"
    assert r.source.id == "nse_debarred" and r.source.as_on


async def test_personal_name_alone_is_not_a_match(make_case, config, fixture_db):
    # "Fraud Operator One" is debarred in the fixture but reads as a personal name: name-only matches need a firm
    r = await NamesScan().check(_msg("Call Fraud Operator One for tips"), _ctx(make_case(), config, fixture_db))
    assert r.status == "clear"


async def test_caution_list_name(make_case, config, fixture_db):
    r = await NamesScan().check(_msg("Best advisory: Quick Profit Advisory, join now"), _ctx(make_case(), config, fixture_db))
    assert r.status == "hit" and "ON_CAUTION_LIST" in [s.code for s in r.signals]
    assert r.facts["caution"][0]["source_url"].startswith("https://")


async def test_clean_text_and_missing_db(make_case, config, fixture_db):
    assert (await NamesScan().check(_msg("Your SIP is due on 5 Oct."), _ctx(make_case(), config, fixture_db))).status == "clear"
    assert (await NamesScan().check(_msg("anything"), _ctx(make_case(), config, None))).status == "unknown"


def test_looks_like_org():
    assert looks_like_org("Pump Masters Pvt Ltd") and looks_like_org("Choudhary Global Limited")
    assert not looks_like_org("Rahul Meena") and not looks_like_org("Rajesh Kumar Sharma")
