"""Social family checkers (LLD §9.7): official broker/AMC/regulator handles."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from satark.checkers.base import BaseChecker, clear, hit, register_checker, unknown
from satark.harness.state import Basis, Entity, SourceRef
from satark.infra.norm import handle_norm

_BRAND_KINDS = {"broker", "amc", "regulator", "exchange"}
_NOT_ALNUM = re.compile(r"[^a-z0-9]")


def _basis(entity: Entity, default: Basis) -> Basis:
    return "llm_claim" if entity.origin == "llm" else default


def _brand_alias_in(handle: str, brands: list[dict]) -> str | None:
    """A brand alias (broker/amc/regulator/exchange) contained in the handle, ignoring punctuation."""
    handle_clean = _NOT_ALNUM.sub("", handle)
    for b in brands:
        if b.get("kind") not in _BRAND_KINDS:
            continue
        for alias in b.get("aliases", []):
            a = _NOT_ALNUM.sub("", alias.lower())
            if a and a in handle_clean:
                return alias
    return None


@register_checker
class SocialOfficialHandles(BaseChecker):
    id, family = "social.official_handles", "social"
    description = "Is this social handle one of a broker's, AMC's or regulator's official accounts?"
    consumes = frozenset({"social.handle", "tg.link"})
    produces = frozenset({"HANDLE_OFFICIAL", "HANDLE_LOOKALIKE_OFFICIAL"})
    needs = ("db",)
    source = "nse_broker_social"

    async def check(self, entity, ctx):
        if entity.type == "tg.link":
            platform, handle = "telegram", handle_norm(ctx.raw(entity))
        else:  # social.handle value is "<platform>:<handle>"
            platform, _, raw_handle = ctx.raw(entity).partition(":")
            platform, handle = platform.lower(), handle_norm(raw_handle)
        if not handle:
            return clear()
        if ctx.db is None or not ctx.db.one("SELECT 1 FROM social_handle LIMIT 1"):
            return unknown("source_missing")

        src = SourceRef(id=self.source, as_on=ctx.db.source_as_on(self.source))
        basis = _basis(entity, "official_list")
        row = ctx.db.one(
            "SELECT entity_name FROM social_handle WHERE platform = ? AND handle_norm = ?", (platform, handle)
        )
        if row:
            return clear("HANDLE_OFFICIAL", basis=basis, source=src, facts={"entity_name": row["entity_name"]})

        for r in ctx.db.query("SELECT handle_norm FROM social_handle WHERE platform = ?", (platform,)):
            if fuzz.ratio(handle, r["handle_norm"]) / 100 >= 0.85:
                return hit(
                    "HANDLE_LOOKALIKE_OFFICIAL", basis=basis, source=src, facts={"looks_like": r["handle_norm"]}
                )
        alias = _brand_alias_in(handle, ctx.config.brands)
        if alias:
            return hit("HANDLE_LOOKALIKE_OFFICIAL", basis=_basis(entity, "rule"), facts={"looks_like": alias})
        return clear()
