"""Payment family checkers (LLD §9.3): UPI handle/QR rules and crypto payment requests."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from rapidfuzz import fuzz

from satark.checkers.base import BaseChecker, CheckContext, clear, hit, register_checker, unknown
from satark.harness.state import Basis, CaseState, Entity, EntityDraft, SourceRef
from satark.infra.norm import name_norm

_VALID_HANDLE_RE = re.compile(r"^([a-z0-9]+(?:\.[a-z0-9]+)*)\.(brk|bti|dp|ra|ia|invit|mf|pms|sreit|reit)@valid([a-z]+)$")
_SUFFIX_CATEGORY = {"brk": "BROKER", "ra": "RA", "ia": "IA", "pms": "PMS", "mf": "MF", "dp": "DP"}
_REGULATED_KINDS = {"regulator", "broker", "amc", "exchange", "depository"}


def _basis(entity: Entity, default: Basis) -> Basis:
    return "llm_claim" if entity.origin == "llm" else default


def _claims_regulated(case: CaseState) -> bool:
    """Does the case claim SEBI registration, or impersonate a regulated kind of firm?"""
    if case.claim("claim.registered_as") is not None:
        return True
    if case.by_type("sebi.reg_no"):
        return True
    return any(c.attrs.get("kind") in _REGULATED_KINDS for c in case.by_type("claim.impersonates"))


@register_checker
class UpiValidHandle(BaseChecker):
    id, family = "upi.valid_handle", "payment"
    description = "Is this UPI ID a SEBI @valid handle, and does its category fit the claim?"
    consumes = frozenset({"upi.vpa"})
    produces = frozenset({"UPI_VALID_HANDLE", "UPI_PERSONAL_WHILE_CLAIMING_SEBI", "UPI_VALID_CATEGORY_MISMATCH"})
    decisive = True

    async def check(self, entity, ctx):
        raw = ctx.raw(entity)
        basis = _basis(entity, "rule")
        m = _VALID_HANDLE_RE.fullmatch(raw)
        if m:
            category = _SUFFIX_CATEGORY.get(m.group(2), "OTHER")
            claim = ctx.case.claim("claim.registered_as")
            claimed_category = claim.attrs.get("category") if claim else None
            if claimed_category and claimed_category != category:
                return hit(
                    "UPI_VALID_CATEGORY_MISMATCH",
                    basis=basis,
                    facts={"category": category, "claimed_category": claimed_category},
                )
            return clear("UPI_VALID_HANDLE", basis=basis, facts={"category": category})
        if _claims_regulated(ctx.case):
            return hit("UPI_PERSONAL_WHILE_CLAIMING_SEBI", basis=basis)
        return clear()


@register_checker
class UpiPsp(BaseChecker):
    id, family = "upi.psp", "payment"
    description = "Look up a UPI handle's bank and probable app."
    consumes = frozenset({"upi.vpa"})
    produces = frozenset({"UPI_HANDLE_UNKNOWN"})
    needs = ("db",)
    source = "psp_handles"

    async def check(self, entity, ctx):
        raw = ctx.raw(entity)
        if "@" not in raw:
            return clear()
        handle = raw.rsplit("@", 1)[-1].lower()
        if not handle:
            return clear()
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM psp_handle LIMIT 1"):
            return unknown("source_missing")
        row = ctx.db.one("SELECT bank, app FROM psp_handle WHERE handle = ?", (handle,))
        src = SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source))
        if row:
            return clear(facts={"bank": row["bank"], "app": row["app"]}, source=src)
        if handle.startswith("valid"):  # a SEBI @valid handle, not a bank PSP handle
            return clear(source=src)
        return hit("UPI_HANDLE_UNKNOWN", basis=_basis(entity, "rule"), source=src)


def _claimed_party_name(ctx: CheckContext) -> str | None:
    names = ctx.case.by_type("party.name")
    return ctx.raw(names[0]) if names else None


@register_checker
class UpiQr(BaseChecker):
    id, family = "upi.qr", "payment"
    description = "Parse a UPI QR/intent payload and check it against the claimed business."
    consumes = frozenset({"upi.uri"})
    produces = frozenset({"QR_P2P_FOR_BUSINESS", "QR_MCC_NOT_SECURITIES", "QR_PAYEE_NAME_MISMATCH", "QR_UNSIGNED"})

    async def check(self, entity, ctx):
        params = parse_qs(urlsplit(ctx.raw(entity)).query)

        def first(key: str) -> str | None:
            v = params.get(key)
            return v[0] if v else None

        pa, pn, mc, sign, url = first("pa"), first("pn"), first("mc"), first("sign"), first("url")
        derived = []
        if pa:
            derived.append(EntityDraft(type="upi.vpa", value=pa))
        if url:
            derived.append(EntityDraft(type="url", value=url))
        facts = {"payee_name_raw": pn or "", "mc": mc, "has_sign": sign is not None}

        codes: list[str] = []
        if _claims_regulated(ctx.case):
            if not mc or mc == "0000":
                codes.append("QR_P2P_FOR_BUSINESS")
            elif mc != "6211":
                codes.append("QR_MCC_NOT_SECURITIES")
            claimed_name = _claimed_party_name(ctx)
            if pn and claimed_name and fuzz.token_set_ratio(name_norm(pn), name_norm(claimed_name)) / 100 < 0.6:
                codes.append("QR_PAYEE_NAME_MISMATCH")
            if sign is None and mc and mc != "0000":
                codes.append("QR_UNSIGNED")

        basis = _basis(entity, "rule")
        if codes:
            return hit(*codes, basis=basis, facts=facts, derived=derived)
        return clear(facts=facts, derived=derived)


_COLLECT_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"approve\s+the\s+request\s+to\s+receive\s+money",
        r"enter\s+(?:your\s+)?upi\s+pin\s+to\s+receive",
        r"collect\s+request\s+to\s+get\s+your\s+(?:refund|profit)",
        r"पैसे\s*पाने\s*के\s*लिए\s*pin\s*डालें",
        r"receive\s+karne\s+ke\s+liye\s+pin",
    )
]


@register_checker
class UpiCollect(BaseChecker):
    id, family = "upi.collect", "payment"
    description = "A UPI collect request framed as receiving money (P2P collect-to-receive ended 1 Oct 2025)."
    consumes = frozenset({"message.text"})
    produces = frozenset({"UPI_COLLECT_TO_RECEIVE"})

    async def check(self, entity, ctx):
        text = ctx.raw(entity)
        if any(p.search(text) for p in _COLLECT_PATTERNS):
            return hit("UPI_COLLECT_TO_RECEIVE", basis=_basis(entity, "rule"))
        return clear()


@register_checker
class CryptoAddress(BaseChecker):
    id, family = "crypto.address", "payment"
    description = "A crypto address alongside a payment claim or a money amount/return-rate entity."
    consumes = frozenset({"crypto.btc", "crypto.evm", "crypto.tron"})
    produces = frozenset({"CRYPTO_PAYMENT_REQUEST"})

    async def check(self, entity, ctx):
        if not entity.valid:
            return clear()
        # Facts/claims only (product decision: no keyword-context gating for this signal).
        payment_context = (
            ctx.case.claim("request.payment") is not None
            or bool(ctx.case.by_type("money.inr"))
            or bool(ctx.case.by_type("money.return_rate"))
        )
        if payment_context:
            return hit("CRYPTO_PAYMENT_REQUEST", basis=_basis(entity, "rule"))
        return clear()
