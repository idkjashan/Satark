"""Tests for the phone checker family (satark/checkers/phone.py)."""

from __future__ import annotations

from datetime import UTC, datetime

from satark.checkers.base import CheckContext
from satark.checkers.phone import PhoneHelpline, PhoneRules, SmsHeader
from satark.harness.state import Entity

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def entity(type_: str, value: str = "", cls: str = "C", **attrs) -> Entity:
    return Entity(id="e1", type=type_, cls=cls, value=value, display=value, attrs=attrs)


def case_with_text(make_case, text: str = ""):
    case = make_case()
    if text:
        case.entities.append(entity("message.text", text))
    return case


def ctx(config, case):
    return CheckContext(case=case, config=config, now=NOW)


def impersonates(**attrs) -> Entity:
    return Entity(id="c1", type="claim.impersonates", cls="P", attrs=attrs)


def registered_as(**attrs) -> Entity:
    return Entity(id="c2", type="claim.registered_as", cls="P", attrs=attrs)


# ---- phone.rules --------------------------------------------------------------------------


async def test_series_1600_is_clear_assurance(config, make_case):
    checker = PhoneRules()
    e = entity("phone", "+911600313384")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and {s.code for s in result.signals} == {"SERIES_1600"}


async def test_phone_series_attr_overrides_classification(config, make_case):
    """If extraction already set attrs.phone_series, trust it instead of recomputing."""
    checker = PhoneRules()
    e = entity("phone", "+919876543210", phone_series="1600")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert {s.code for s in result.signals} == {"SERIES_1600"}


async def test_foreign_number_with_regulated_claim_hits(config, make_case):
    checker = PhoneRules()
    case = case_with_text(make_case)
    case.entities.append(impersonates(kind="broker", brand_id="zerodha"))
    e = entity("phone", "+447911123456")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"FOREIGN_NUMBER_OFFICIAL_CLAIM"}


async def test_foreign_number_with_registration_claim_hits(config, make_case):
    checker = PhoneRules()
    case = case_with_text(make_case)
    case.entities.append(registered_as(regulator="SEBI", category="IA"))
    e = entity("phone", "+447911123456")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"FOREIGN_NUMBER_OFFICIAL_CLAIM"}


async def test_foreign_number_without_claim_is_clear(config, make_case):
    checker = PhoneRules()
    e = entity("phone", "+14155552671")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and not result.signals


async def test_140_series_for_service_claim_hits(config, make_case):
    """Grounded in a structured claim (request.kyc_docs), not a text-keyword scan."""
    checker = PhoneRules()
    case = case_with_text(make_case, "Please call this number to continue.")
    case.entities.append(Entity(id="c3", type="request.kyc_docs", cls="P"))
    e = entity("phone", "+911401234567")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"PROMO_140_FOR_SERVICE"}


async def test_140_series_falls_back_to_keywords_when_no_claims_extracted(config, make_case):
    """No structured claim exists for 'presents a service/transaction' in general, so a precise
    keyword scan is the documented fallback when nothing was extracted."""
    checker = PhoneRules()
    case = case_with_text(make_case, "Your bank KYC is pending, call us to update your account.")
    e = entity("phone", "+911401234567")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"PROMO_140_FOR_SERVICE"}


async def test_140_series_pure_promo_is_clear(config, make_case):
    checker = PhoneRules()
    case = case_with_text(make_case, "Flat 50% off on our new course, limited time offer!")
    e = entity("phone", "+911401234567")
    result = await checker.check(e, ctx(config, case))
    assert result.status == "clear" and not result.signals


async def test_mobile_for_regulated_firm_past_deadline_hits(config, make_case):
    checker = PhoneRules()
    case = case_with_text(make_case)
    case.entities.append(impersonates(kind="bank", brand_id="hdfcbank"))  # deadline 2026-01-01, now 2026-10-03
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"REGULATED_CALL_NOT_1600"}
    assert result.facts["kind"] == "bank"


async def test_mobile_for_regulated_firm_before_deadline_is_clear(config, make_case):
    checker = PhoneRules()
    case = case_with_text(make_case)
    case.entities.append(impersonates(kind="broker", brand_id="zerodha"))  # deadline 2026-03-15
    e = entity("phone", "+919876543210")
    early = CheckContext(case=case, config=config, now=datetime(2026, 1, 1, tzinfo=UTC))
    result = await checker.check(e, early)
    assert result.status == "clear" and not result.signals


async def test_ordinary_mobile_without_claim_is_clear(config, make_case):
    checker = PhoneRules()
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and not result.signals


# ---- phone.helpline -----------------------------------------------------------------------


async def test_official_helpline_number_is_clear_assurance(config, make_case):
    checker = PhoneHelpline()
    e = entity("phone", "1930")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and {s.code for s in result.signals} == {"OFFICIAL_HELPLINE"}


async def test_sebi_toll_free_is_recognised(config, make_case):
    checker = PhoneHelpline()
    e = entity("phone", "+911800227575")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert {s.code for s in result.signals} == {"OFFICIAL_HELPLINE"}


async def test_fake_helpline_falls_back_to_keywords_when_no_claims_extracted(config, make_case):
    checker = PhoneHelpline()
    case = case_with_text(make_case, "This is the official SEBI helpline toll free number, call now.")
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"FAKE_HELPLINE"}


async def test_fake_helpline_grounded_in_impersonation_claim(config, make_case):
    """No brand named in the text itself; claim.impersonates(kind=regulator) grounds it instead."""
    checker = PhoneHelpline()
    case = case_with_text(make_case, "This is our official helpline, toll free, call now.")
    case.entities.append(impersonates(kind="regulator", brand_id="sebi"))
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"FAKE_HELPLINE"}


async def test_fake_helpline_suppressed_when_claim_is_unrelated(config, make_case):
    """An extracted impersonation claim of an unrelated kind (celebrity) takes precedence over
    a stray keyword match: we trust the structured claim, not a loose word in passing."""
    checker = PhoneHelpline()
    case = case_with_text(make_case, "Unlike the fake SEBI apps, our helpline toll free number is real.")
    case.entities.append(impersonates(kind="celebrity", brand_id="musk"))
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case))
    assert result.status == "clear" and not result.signals


async def test_ordinary_number_no_helpline_claim_is_clear(config, make_case):
    checker = PhoneHelpline()
    case = case_with_text(make_case, "Call me when you are free")
    e = entity("phone", "+919876543210")
    result = await checker.check(e, ctx(config, case))
    assert result.status == "clear" and not result.signals


# ---- sms.header ---------------------------------------------------------------------------


async def test_promotional_header_for_transactional_message_hits(config, make_case):
    checker = SmsHeader()
    case = case_with_text(make_case, "Your OTP for login is 123456, do not share it with anyone.")
    e = entity("sms.header", "VM-HDFCBK-P")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"HEADER_CATEGORY_MISMATCH"}


async def test_promotional_header_grounded_in_credentials_claim(config, make_case):
    """Grounded in a structured request.credentials claim rather than scanning the text."""
    checker = SmsHeader()
    case = case_with_text(make_case, "Please respond within 5 minutes.")
    case.entities.append(Entity(id="c4", type="request.credentials", cls="P", attrs={"kind": "otp"}))
    e = entity("sms.header", "VM-HDFCBK-P")
    result = await checker.check(e, ctx(config, case))
    assert {s.code for s in result.signals} == {"HEADER_CATEGORY_MISMATCH"}


async def test_promotional_header_for_promo_message_is_clear(config, make_case):
    checker = SmsHeader()
    case = case_with_text(make_case, "Flat 20% cashback on your next trade, limited period offer.")
    e = entity("sms.header", "VM-HDFCBK-P")
    result = await checker.check(e, ctx(config, case))
    assert result.status == "clear" and not result.signals


async def test_government_header_for_non_government_brand_hits(config, make_case):
    checker = SmsHeader()
    e = entity("sms.header", "VM-ZERDHA-G")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert {s.code for s in result.signals} == {"HEADER_CATEGORY_MISMATCH"}


async def test_government_header_for_government_brand_is_clear(config, make_case):
    checker = SmsHeader()
    e = entity("sms.header", "VM-SEBIND-G")
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and not result.signals


async def test_header_not_matching_shape_is_clear(config, make_case):
    checker = SmsHeader()
    e = entity("sms.header", "VM-HDFCBK")  # no category suffix
    result = await checker.check(e, ctx(config, case_with_text(make_case)))
    assert result.status == "clear" and not result.signals
