"""Phone family checkers (LLD §9.6): TRAI series rules, the official helpline allow-list,
and DLT SMS header category mismatches. No DB or network: everything here is config + regex."""

from __future__ import annotations

import re
from datetime import date

from rapidfuzz import fuzz

from satark.checkers.base import BaseChecker, CheckContext, clear, hit, register_checker
from satark.harness.state import CaseState, CheckResult, Entity

_REGULATED_KINDS = frozenset({"regulator", "broker", "bank", "exchange", "amc"})
_TRANSACTIONAL_CLAIM_TYPES = ("request.credentials", "request.kyc_docs", "request.payment")
# Keyword fallbacks below are used only where no claim type covers the meaning (an unextracted
# or deterministic-only case), per product direction: ground decisions in entities/claims first.
_HELPLINE_WORDS = re.compile(r"(?i)helpline|customer\s*care|toll[-\s]?free|हेल्पलाइन|कस्टमर\s*केयर|टोल\s*फ्री")
_HELPLINE_BRANDS = re.compile(r"(?i)\bsebi\b|\brbi\b|\bbank\b|cyber|सेबी|आरबीआई|बैंक|साइबर")
_TRANSACTIONAL_WORDS = re.compile(
    r"(?i)\botp\b|\bkyc\b|\baccount\b|\btransaction\b|\bdebit(ed)?\b|\bcredit(ed)?\b|\bverify\b|केवाईसी|ओटीपी|खाता"
)
_HEADER_RE = re.compile(r"^[A-Z]{2}-([A-Z0-9]{6,11})-([PSTG])$")


def _message_text(ctx: CheckContext) -> str:
    msgs = ctx.case.by_type("message.text")
    return ctx.raw(msgs[0]) if msgs else ""


def _local_digits(raw: str) -> str:
    if raw.startswith("+91"):
        return raw[3:]
    return "" if raw.startswith("+") else re.sub(r"\D", "", raw)


def _phone_series(entity: Entity, raw: str) -> str:
    """attrs.phone_series from extraction if present, else a same-shape classification here."""
    series = entity.attrs.get("phone_series")
    if series:
        return series
    if raw.startswith("+") and not raw.startswith("+91"):
        return "foreign"
    local = _local_digits(raw)
    if len(local) == 10 and local.startswith("1600"):
        return "1600"
    if len(local) == 10 and local.startswith("140"):
        return "140"
    if local.startswith("1800") or local.startswith("180"):
        return "1800"
    if re.fullmatch(r"[6-9]\d{9}", local):
        return "mobile"
    if len(local) <= 6:
        return "short_code"
    return "other"


def _impersonates_regulated(case: CaseState) -> bool:
    return any(c.attrs.get("kind") in _REGULATED_KINDS for c in case.by_type("claim.impersonates"))


def _looks_transactional(case: CaseState, text: str) -> bool:
    """A bank/broker service or transaction is in play: grounded first in extracted claims
    (an OTP/credential request, a KYC request, a payment ask, or impersonating a bank/broker);
    falls back to a narrow keyword scan only when no such claim was extracted at all."""
    if any(case.by_type(t) for t in _TRANSACTIONAL_CLAIM_TYPES):
        return True
    if any(c.attrs.get("kind") in ("bank", "broker") for c in case.by_type("claim.impersonates")):
        return True
    return bool(_TRANSACTIONAL_WORDS.search(text))


def _claims_official_helpline(case: CaseState, text: str) -> bool:
    """The text calls a number a SEBI/RBI/bank/cyber helpline. 'Helpline/customer care/toll
    free' has no claim type of its own, so that part stays a keyword scan; which brand is
    being invoked is grounded in claim.impersonates when extraction found one."""
    if not _HELPLINE_WORDS.search(text):
        return False
    impersonates = case.by_type("claim.impersonates")
    if impersonates:
        return any(c.attrs.get("kind") in ("regulator", "bank") for c in impersonates)
    return bool(_HELPLINE_BRANDS.search(text))  # nothing extracted at all: fall back to keywords


def _regulated_past_deadline(case: CaseState, now, deadlines: dict) -> Entity | None:
    for claim in case.by_type("claim.impersonates"):
        deadline = deadlines.get(claim.attrs.get("kind"))
        if deadline and now.date() >= date.fromisoformat(deadline):
            return claim
    return None


def _is_government_brand(brand_part: str, brands: list[dict]) -> bool:
    key = re.sub(r"[^A-Z0-9]", "", brand_part.upper())
    if not key:
        return False
    for b in brands:
        if b.get("kind") not in ("government", "regulator"):
            continue
        for candidate in (b.get("id", ""), *b.get("aliases", ())):
            c = re.sub(r"[^A-Z0-9]", "", str(candidate).upper())
            if c and (c == key or c in key or key in c or fuzz.partial_ratio(c, key) >= 80):
                return True
    return False


# ---- phone.rules --------------------------------------------------------------------------


@register_checker
class PhoneRules(BaseChecker):
    id, family = "phone.rules", "phone"
    description = "Classifies a phone number's series (1600/140/mobile/foreign) against TRAI rules and the case's claims."
    consumes = frozenset({"phone"})
    produces = frozenset(
        {"SERIES_1600", "FOREIGN_NUMBER_OFFICIAL_CLAIM", "PROMO_140_FOR_SERVICE", "REGULATED_CALL_NOT_1600"}
    )
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        raw = ctx.raw(entity)
        series = _phone_series(entity, raw)
        case = ctx.case
        if series == "1600":
            return clear("SERIES_1600", basis="rule")
        if series == "foreign":
            if _impersonates_regulated(case) or case.claim("claim.registered_as") is not None:
                return hit("FOREIGN_NUMBER_OFFICIAL_CLAIM", basis="rule")
            return clear()
        if series == "140":
            if _looks_transactional(case, _message_text(ctx)):
                return hit("PROMO_140_FOR_SERVICE", basis="rule")
            return clear()
        if series == "mobile":
            claim = _regulated_past_deadline(case, ctx.now, ctx.config.phone_rules.get("sector_deadlines", {}))
            if claim:
                return hit("REGULATED_CALL_NOT_1600", basis="rule", facts={"kind": claim.attrs.get("kind")})
            return clear()
        return clear()


# ---- phone.helpline -----------------------------------------------------------------------


@register_checker
class PhoneHelpline(BaseChecker):
    id, family = "phone.helpline", "phone"
    description = "Is this number on our list of official SEBI/RBI/IRDAI/cyber-fraud helplines?"
    consumes = frozenset({"phone"})
    produces = frozenset({"OFFICIAL_HELPLINE", "FAKE_HELPLINE"})
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        raw = ctx.raw(entity)
        helplines = ctx.config.phone_rules.get("helplines", {})
        info = helplines.get(raw)
        if info:
            return clear("OFFICIAL_HELPLINE", basis="rule", facts={"name": info.get("name")})
        if _claims_official_helpline(ctx.case, _message_text(ctx)):
            return hit("FAKE_HELPLINE", basis="rule")
        return clear()


# ---- sms.header ---------------------------------------------------------------------------


@register_checker
class SmsHeader(BaseChecker):
    id, family = "sms.header", "phone"
    description = "Does a DLT SMS header's category suffix (-P promotional, -G government) match the message?"
    consumes = frozenset({"sms.header"})
    produces = frozenset({"HEADER_CATEGORY_MISMATCH"})
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        raw = ctx.raw(entity)
        m = _HEADER_RE.match(raw)
        if not m:
            return clear()
        brand_part, suffix = m.group(1), m.group(2)
        if suffix == "P" and _looks_transactional(ctx.case, _message_text(ctx)):
            return hit("HEADER_CATEGORY_MISMATCH", basis="rule", facts={"suffix": "P", "header_raw": raw})
        if suffix == "G" and not _is_government_brand(brand_part, ctx.config.brands):
            return hit("HEADER_CATEGORY_MISMATCH", basis="rule", facts={"suffix": "G", "header_raw": raw})
        return clear()
