"""Registry family checkers (LLD §9.2): SEBI registration numbers, caution lists, debarred entities.

sebi.reg.format and sebi.reg.lookup share the same format regex so a malformed number is reported
once (by sebi.reg.format) and the lookup/name-match checkers just clear() on a bad format.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from satark.checkers.base import BaseChecker, CheckContext, clear, hit, register_checker, unknown
from satark.harness.state import Basis, CaseState, Entity, SourceRef
from satark.infra.norm import (
    handle_norm,
    looks_like_org,
    name_norm,
    phone_norm,
    reg_norm,
    registrable_domain,
    sha256_hex,
    upi_norm,
)

# LLD §8.2 R5: category is implied by the prefix, so one regex covers "strict format per category".
_REG_NO_RE = re.compile(
    r"^(?:IN[AHZPMRBFE]\d{9}|INBI\d{8}|IND\d{9}|"
    r"IN-DP-(?:(?:CDSL|NSDL)-)?\d{1,4}-(?:\d{2}|\d{4})|"
    r"MF/\d{3}/\d{2}/\d{1,2}|"
    r"IN/(?:AIF[1-3]|REIT|SM-REIT|InvIT|VCF|FVCI)/\d{2}-\d{2}/\d{2,5}|"
    r"IN/(?:CRA|KRA)/\d{3}/\d{4}|IN/CUS/\d{3})$"
)


def _basis(entity: Entity, default: Basis) -> Basis:
    return "llm_claim" if entity.origin == "llm" else default


def _refs_of_type(case: CaseState, entity: Entity, type_: str) -> list[Entity]:
    out = []
    for ref in entity.refs:
        e = case.entity(ref)
        if e is not None and e.type == type_:
            out.append(e)
    return out


@register_checker
class SebiRegFormat(BaseChecker):
    id, family = "sebi.reg.format", "registry"
    description = "Strict SEBI registration-number format per category prefix (LLD Appendix C.3)."
    consumes = frozenset({"sebi.reg_no"})
    produces = frozenset({"REG_FORMAT_INVALID"})
    decisive = True

    async def check(self, entity: Entity, ctx: CheckContext):
        raw = reg_norm(ctx.raw(entity))
        if _REG_NO_RE.fullmatch(raw):
            return clear()
        return hit("REG_FORMAT_INVALID", basis=_basis(entity, "rule"))


@register_checker
class SebiRegLookup(BaseChecker):
    id, family = "sebi.reg.lookup", "registry"
    description = "Exact match of a SEBI registration number in the daily register export."
    consumes = frozenset({"sebi.reg_no"})
    produces = frozenset({"REG_FOUND", "REG_EXPIRED", "REG_NOT_FOUND"})
    needs = ("db",)
    source = "sebi_registers"
    cache_ttl_s = -1
    decisive = True

    async def check(self, entity, ctx):
        raw = reg_norm(ctx.raw(entity))
        if not _REG_NO_RE.fullmatch(raw):
            return clear()  # sebi.reg.format already reports the format problem
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM intermediary LIMIT 1"):
            return unknown("source_missing")
        # ponytail: a reg_no can appear once per segment file (schema.sql comment); we take the
        # first row. Upgrade to "any non-expired row wins" if a real duplicate causes a bad verdict.
        rows = ctx.db.query(
            "SELECT category, name, trade_name, valid_to FROM intermediary WHERE reg_no = ?", (raw,)
        )
        src = SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source))
        basis = _basis(entity, "registry")
        if not rows:
            return hit("REG_NOT_FOUND", basis=basis, source=src)
        row = rows[0]
        facts = {
            "registered_name": row["name"],
            "category": row["category"],
            "valid_to": row["valid_to"],
            "trade_name": row["trade_name"],
        }
        if row["valid_to"] and row["valid_to"] != "perpetual" and row["valid_to"] < ctx.now.date().isoformat():
            return hit("REG_EXPIRED", basis=basis, source=src, facts=facts)
        return clear("REG_FOUND", basis=basis, source=src, facts=facts)


@register_checker
class SebiRegNameMatch(BaseChecker):
    id, family = "sebi.reg.name_match", "registry"
    description = "Does the claimed name match the name registered against the claimed SEBI number?"
    consumes = frozenset({"claim.registered_as"})
    produces = frozenset(
        {"REG_NAME_MISMATCH", "REG_CATEGORY_MISMATCH", "REG_FOUND", "AMBIGUOUS_MATCH"}
    )
    needs = ("db",)
    decisive = True

    def should_run(self, entity, case):
        return bool(_refs_of_type(case, entity, "party.name")) and bool(_refs_of_type(case, entity, "sebi.reg_no"))

    async def check(self, entity, ctx):
        names = _refs_of_type(ctx.case, entity, "party.name")
        regs = _refs_of_type(ctx.case, entity, "sebi.reg_no")
        if not names or not regs:
            return clear()
        name_entity, reg_entity = names[0], regs[0]
        raw_reg = reg_norm(ctx.raw(reg_entity))
        if not _REG_NO_RE.fullmatch(raw_reg):
            return clear()  # sebi.reg.format reports this
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM intermediary LIMIT 1"):
            return unknown("source_missing")
        rows = ctx.db.query("SELECT category, name, trade_name FROM intermediary WHERE reg_no = ?", (raw_reg,))
        if not rows:
            return clear()  # sebi.reg.lookup reports REG_NOT_FOUND
        claimed_raw = ctx.raw(name_entity)
        claimed_norm = name_norm(claimed_raw)
        basis = _basis(entity, "registry")

        best_ratio, best_row = -1.0, rows[0]
        for row in rows:
            for candidate in (row["name"], row["trade_name"]):
                if not candidate:
                    continue
                ratio = fuzz.token_set_ratio(claimed_norm, name_norm(candidate)) / 100
                if ratio > best_ratio:
                    best_ratio, best_row = ratio, row

        if best_ratio < 0.75:
            return hit(
                "REG_NAME_MISMATCH",
                basis=basis,
                facts={"registered_name": best_row["name"], "claimed_name_raw": claimed_raw},
            )
        claimed_category = entity.attrs.get("category")
        if claimed_category and claimed_category != best_row["category"]:
            return hit(
                "REG_CATEGORY_MISMATCH",
                basis=basis,
                facts={
                    "registered_name": best_row["name"],
                    "category": best_row["category"],
                    "claimed_category": claimed_category,
                },
            )
        if best_ratio < 0.90:
            candidates = [{"reg_no": raw_reg, "name": r["name"], "category": r["category"]} for r in rows]
            return clear(flags={"AMBIGUOUS_MATCH"}, facts={"candidates": candidates})
        return clear(
            "REG_FOUND", basis=basis, facts={"registered_name": best_row["name"], "category": best_row["category"]}
        )


@register_checker
class SebiRegistrySearch(BaseChecker):
    id, family = "sebi.registry.search", "registry"
    description = "Full-text search of the SEBI register by claimed name when no number was given."
    consumes = frozenset({"claim.registered_as"})
    produces = frozenset({"REG_FOUND", "AMBIGUOUS_MATCH", "REG_CLAIM_NOT_FOUND"})
    needs = ("db",)

    def should_run(self, entity, case):
        return bool(_refs_of_type(case, entity, "party.name")) and not _refs_of_type(case, entity, "sebi.reg_no")

    async def check(self, entity, ctx):
        names = _refs_of_type(ctx.case, entity, "party.name")
        if not names or _refs_of_type(ctx.case, entity, "sebi.reg_no"):
            return clear()
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM intermediary LIMIT 1"):
            return unknown("source_missing")

        claimed_norm = name_norm(ctx.raw(names[0]))
        basis = _basis(entity, "registry")
        tokens = [t.replace('"', '""') for t in claimed_norm.split() if t]
        if not tokens:
            return hit("REG_CLAIM_NOT_FOUND", basis=basis)
        query = " OR ".join(f'"{t}"' for t in tokens)  # sanitised: every token quoted for FTS5
        rows = ctx.db.query(
            "SELECT i.reg_no, i.name, i.trade_name, i.category FROM intermediary_fts f "
            "JOIN intermediary i ON i.id = f.rowid WHERE f.intermediary_fts MATCH ? LIMIT 25",
            (query,),
        )
        if not rows:
            return hit("REG_CLAIM_NOT_FOUND", basis=basis)

        def ratio_of(row) -> float:
            best = fuzz.token_set_ratio(claimed_norm, name_norm(row["name"]))
            if row["trade_name"]:
                best = max(best, fuzz.token_set_ratio(claimed_norm, name_norm(row["trade_name"])))
            return best / 100

        ranked = sorted(rows, key=ratio_of, reverse=True)[:3]
        best = ranked[0]
        best_ratio = ratio_of(best)
        if best_ratio >= 0.90:
            return clear(
                "REG_FOUND",
                basis=basis,
                facts={"registered_name": best["name"], "reg_no": best["reg_no"], "category": best["category"]},
            )
        if best_ratio >= 0.75:
            candidates = [{"reg_no": r["reg_no"], "name": r["name"], "category": r["category"]} for r in ranked]
            return clear(flags={"AMBIGUOUS_MATCH"}, facts={"candidates": candidates})
        return hit("REG_CLAIM_NOT_FOUND", basis=basis)


@register_checker
class SebiDebarred(BaseChecker):
    id, family = "sebi.debarred", "registry"
    description = "Exact match of a name or PAN against SEBI-debarred entities (NSE snapshot)."
    consumes = frozenset({"party.name", "pan"})
    produces = frozenset({"DEBARRED_ENTITY"})
    needs = ("db",)
    source = "nse_debarred"

    async def check(self, entity, ctx):
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM debarred LIMIT 1"):
            return unknown("source_missing")
        src = SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source))
        basis = _basis(entity, "official_list")

        if entity.type == "pan":
            digest = sha256_hex(ctx.raw(entity).upper())
            row = ctx.db.one(
                "SELECT order_ref, order_date, period FROM debarred WHERE pan_sha256 = ? AND revoked = 0", (digest,)
            )
        else:
            claimed = name_norm(ctx.raw(entity))
            if len(claimed.split()) < 2 or len(claimed) < 8:
                return clear()  # avoid common-name false alarms
            rows = ctx.db.query(
                "SELECT name, order_ref, order_date, period FROM debarred WHERE name_norm = ? AND revoked = 0", (claimed,)
            )
            # a bare personal name ("Rahul Meena") does not identify a person; only firms match by name
            row = next((r for r in rows if looks_like_org(r["name"])), None)
        if not row:
            return clear()
        return hit(
            "DEBARRED_ENTITY",
            basis=basis,
            source=src,
            facts={"order_ref": row["order_ref"], "order_date": row["order_date"], "period": row["period"]},
        )


# entity type -> (caution_entry.entry_type, normaliser)
_CAUTION_TYPES: dict[str, str] = {
    "party.name": "name",
    "phone": "phone",
    "domain": "domain",
    "url": "domain",
    "upi.vpa": "upi",
    "tg.link": "telegram",
    "social.handle": "handle",
    "app.package": "app",
}


def _caution_value_norm(entity: Entity, ctx: CheckContext) -> str:
    raw = ctx.raw(entity)
    if entity.type == "party.name":
        return name_norm(raw)
    if entity.type == "phone":
        return phone_norm(raw)
    if entity.type in ("domain", "url"):
        return registrable_domain(raw)
    if entity.type == "upi.vpa":
        return upi_norm(raw)
    if entity.type == "tg.link":
        return handle_norm(raw)
    if entity.type == "social.handle":
        return handle_norm(raw.split(":", 1)[-1])
    return raw.strip().lower()  # app.package


@register_checker
class CautionMatch(BaseChecker):
    id, family = "caution.match", "registry"
    description = "Exact match against official caution/alert lists (NSE, BSE, RBI, IRDAI, FIU-IND...)."
    consumes = frozenset(_CAUTION_TYPES)
    produces = frozenset({"ON_CAUTION_LIST"})
    needs = ("db",)
    source = "caution_lists"

    async def check(self, entity, ctx):
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM caution_entry LIMIT 1"):
            return unknown("source_missing")
        value_norm = _caution_value_norm(entity, ctx)
        if not value_norm:
            return clear()
        entry_type = _CAUTION_TYPES[entity.type]
        row = ctx.db.one(
            "SELECT list_id, display, source_url FROM caution_entry WHERE entry_type = ? AND value_norm = ?",
            (entry_type, value_norm),
        )
        if not row:
            return clear()
        return hit(
            "ON_CAUTION_LIST",
            basis=_basis(entity, "official_list"),
            source=SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source)),
            facts={"list_id": row["list_id"], "source_url": row["source_url"], "display": row["display"]},
        )
