"""Unit tests for satark/checkers/payment.py against the fixture DB."""

from __future__ import annotations

from pydantic import SecretStr

from satark.checkers.base import CheckContext
from satark.checkers.payment import CryptoAddress, UpiCollect, UpiPsp, UpiQr, UpiValidHandle
from satark.harness.state import CaseState, Entity, utcnow


def _entity(id_: str, type_: str, value: str, cls: str = "C", **kw) -> Entity:
    return Entity(id=id_, type=type_, cls=cls, value=SecretStr(value), display=value, **kw)


def _case(*entities: Entity) -> CaseState:
    case = CaseState(case_id="t", expires_at=utcnow())
    case.entities.extend(entities)
    return case


def _ctx(case: CaseState, config, db=None) -> CheckContext:
    return CheckContext(case=case, config=config, db=db)


# ======================================================================== upi.valid_handle


async def test_valid_handle_clear_no_claim(config):
    e = _entity("e1", "upi.vpa", "ramesh.ia@validsbi")
    res = await UpiValidHandle().check(e, _ctx(_case(e), config))
    assert res.status == "clear" and [s.code for s in res.signals] == ["UPI_VALID_HANDLE"]
    assert res.facts["category"] == "IA"


async def test_valid_handle_category_mismatch(config):
    e = _entity("e1", "upi.vpa", "ramesh.ia@validsbi")
    claim = _entity("e2", "claim.registered_as", "", cls="P", attrs={"category": "RA"})
    res = await UpiValidHandle().check(e, _ctx(_case(e, claim), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_VALID_CATEGORY_MISMATCH"]


async def test_valid_handle_personal_while_claiming_sebi(config):
    e = _entity("e1", "upi.vpa", "someone@ybl")
    claim = _entity("e2", "claim.registered_as", "", cls="P")
    res = await UpiValidHandle().check(e, _ctx(_case(e, claim), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_PERSONAL_WHILE_CLAIMING_SEBI"]


async def test_valid_handle_personal_no_claim_is_clear(config):
    e = _entity("e1", "upi.vpa", "someone@ybl")
    res = await UpiValidHandle().check(e, _ctx(_case(e), config))
    assert res.status == "clear" and not res.signals


async def test_valid_handle_regulated_via_sebi_reg_no_entity(config):
    e = _entity("e1", "upi.vpa", "someone@ybl")
    reg = _entity("e2", "sebi.reg_no", "INH000000002")
    res = await UpiValidHandle().check(e, _ctx(_case(e, reg), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_PERSONAL_WHILE_CLAIMING_SEBI"]


async def test_valid_handle_regulated_via_impersonation(config):
    e = _entity("e1", "upi.vpa", "someone@ybl")
    imp = _entity("e2", "claim.impersonates", "", cls="P", attrs={"kind": "broker", "org": "Zerodha"})
    res = await UpiValidHandle().check(e, _ctx(_case(e, imp), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_PERSONAL_WHILE_CLAIMING_SEBI"]


# ======================================================================== upi.psp


async def test_psp_known_handle(config, fixture_db):
    e = _entity("e1", "upi.vpa", "someone@okaxis")
    res = await UpiPsp().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and res.facts == {"bank": "Axis Bank", "app": "Google Pay"}


async def test_psp_valid_handle_not_in_table_is_clear(config, fixture_db):
    e = _entity("e1", "upi.vpa", "ramesh.ia@validsbi")  # not a bank PSP handle, but starts with "valid"
    res = await UpiPsp().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_psp_unknown_handle(config, fixture_db):
    e = _entity("e1", "upi.vpa", "someone@okaxls")  # look-alike of okaxis
    res = await UpiPsp().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_HANDLE_UNKNOWN"]


async def test_psp_no_at_sign_clears(config, fixture_db):
    e = _entity("e1", "upi.vpa", "garbage")
    res = await UpiPsp().check(e, _ctx(_case(e), config, fixture_db))
    assert res.status == "clear" and not res.signals


async def test_psp_source_missing(config):
    e = _entity("e1", "upi.vpa", "someone@okaxis")
    res = await UpiPsp().check(e, _ctx(_case(e), config, db=None))
    assert res.status == "unknown" and res.reason == "source_missing"


# ======================================================================== upi.qr


def _qr_case(uri: str, *, business_claim: bool = True, party_name: str | None = None):
    qr_e = _entity("e1", "upi.uri", uri)
    extra = []
    if business_claim:
        extra.append(_entity("e2", "claim.registered_as", "", cls="P"))
    if party_name:
        extra.append(_entity("e3", "party.name", party_name))
    return qr_e, _case(qr_e, *extra)


async def test_qr_p2p_for_business(config):
    qr, case = _qr_case("upi://pay?pa=x@ybl&pn=Someone")
    res = await UpiQr().check(qr, _ctx(case, config))
    assert "QR_P2P_FOR_BUSINESS" in [s.code for s in res.signals]
    assert any(d.type == "upi.vpa" and d.value == "x@ybl" for d in res.derived)


async def test_qr_mcc_not_securities(config):
    qr, case = _qr_case("upi://pay?pa=x@ybl&pn=Someone&mc=1234&sign=abc")
    res = await UpiQr().check(qr, _ctx(case, config))
    assert "QR_MCC_NOT_SECURITIES" in [s.code for s in res.signals]


async def test_qr_payee_name_mismatch(config):
    qr, case = _qr_case(
        "upi://pay?pa=x@validsbi&pn=Totally+Unrelated+Name&mc=6211&sign=abc", party_name="Rajesh Kumar Sharma"
    )
    res = await UpiQr().check(qr, _ctx(case, config))
    assert "QR_PAYEE_NAME_MISMATCH" in [s.code for s in res.signals]


async def test_qr_unsigned(config):
    qr, case = _qr_case("upi://pay?pa=x@validsbi&pn=Rajesh+Kumar+Sharma&mc=6211", party_name="Rajesh Kumar Sharma")
    res = await UpiQr().check(qr, _ctx(case, config))
    assert "QR_UNSIGNED" in [s.code for s in res.signals]


async def test_qr_clean_merchant_qr_is_clear(config):
    qr, case = _qr_case(
        "upi://pay?pa=x@validsbi&pn=Rajesh+Kumar+Sharma&mc=6211&sign=abc", party_name="Rajesh Kumar Sharma"
    )
    res = await UpiQr().check(qr, _ctx(case, config))
    assert res.status == "clear" and not res.signals


async def test_qr_no_business_claim_is_clear(config):
    qr, case = _qr_case("upi://pay?pa=x@ybl&pn=Someone", business_claim=False)
    res = await UpiQr().check(qr, _ctx(case, config))
    assert res.status == "clear" and not res.signals


async def test_qr_derives_url_param(config):
    qr, case = _qr_case("upi://pay?pa=x@ybl&pn=Someone&url=https://inv.example/x", business_claim=False)
    res = await UpiQr().check(qr, _ctx(case, config))
    assert any(d.type == "url" and d.value == "https://inv.example/x" for d in res.derived)


# ======================================================================== upi.collect


async def test_collect_english(config):
    e = _entity("e1", "message.text", "Please approve the request to receive money now")
    res = await UpiCollect().check(e, _ctx(_case(e), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["UPI_COLLECT_TO_RECEIVE"]


async def test_collect_hindi(config):
    e = _entity("e1", "message.text", "पैसे पाने के लिए PIN डालें")
    res = await UpiCollect().check(e, _ctx(_case(e), config))
    assert res.status == "hit"


async def test_collect_hinglish(config):
    e = _entity("e1", "message.text", "Refund receive karne ke liye PIN enter karo")
    res = await UpiCollect().check(e, _ctx(_case(e), config))
    assert res.status == "hit"


async def test_collect_benign(config):
    e = _entity("e1", "message.text", "Thank you for your payment, have a nice day")
    res = await UpiCollect().check(e, _ctx(_case(e), config))
    assert res.status == "clear" and not res.signals


# ======================================================================== crypto.address


async def test_crypto_payment_request_via_claim(config):
    addr = _entity("e1", "crypto.btc", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    payment = _entity("e2", "request.payment", "", cls="P")
    res = await CryptoAddress().check(addr, _ctx(_case(addr, payment), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["CRYPTO_PAYMENT_REQUEST"]


async def test_crypto_payment_request_via_money_amount(config):
    addr = _entity("e1", "crypto.tron", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    amount = _entity("e2", "money.inr", "50000", cls="P")
    res = await CryptoAddress().check(addr, _ctx(_case(addr, amount), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["CRYPTO_PAYMENT_REQUEST"]


async def test_crypto_payment_request_via_return_rate(config):
    addr = _entity("e1", "crypto.tron", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    rate = _entity("e2", "money.return_rate", "0.05/day", cls="P", attrs={"rate": 0.05, "period": "day"})
    res = await CryptoAddress().check(addr, _ctx(_case(addr, rate), config))
    assert res.status == "hit" and [s.code for s in res.signals] == ["CRYPTO_PAYMENT_REQUEST"]


async def test_crypto_keyword_text_alone_is_clear(config):
    # product decision: message wording alone must not gate this signal, only claims/money entities.
    addr = _entity("e1", "crypto.tron", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    text = _entity("e2", "message.text", "Please deposit USDT to this address to start investing")
    res = await CryptoAddress().check(addr, _ctx(_case(addr, text), config))
    assert res.status == "clear" and not res.signals


async def test_crypto_no_payment_context_is_clear(config):
    addr = _entity("e1", "crypto.evm", "0x" + "ab" * 20)
    text = _entity("e2", "message.text", "Here is my wallet address for reference")
    res = await CryptoAddress().check(addr, _ctx(_case(addr, text), config))
    assert res.status == "clear" and not res.signals


async def test_crypto_invalid_address_is_clear(config):
    addr = _entity("e1", "crypto.btc", "garbage", valid=False)
    payment = _entity("e2", "request.payment", "", cls="P")
    res = await CryptoAddress().check(addr, _ctx(_case(addr, payment), config))
    assert res.status == "clear" and not res.signals
