"""names.scan: look for names from official lists anywhere in the message (registry family).

The name checkers in sebi.py need a party.name entity, which usually comes from the AI model. This
checker needs no model: it slides 1–6-word windows over the normalised message and looks them up, so
"invest with Pump Masters Pvt Ltd" or "trade on PrimeXBT" is caught offline too. It is a lookup against
official lists, not a guess: a window must equal a listed name exactly (after normalisation).
Only firm/platform names count — a bare personal name does not identify a person (see norm.looks_like_org).
"""

from __future__ import annotations

from satark.checkers.base import BaseChecker, CheckContext, clear, hit, register_checker, unknown
from satark.harness.state import Entity, SourceRef
from satark.infra.norm import looks_like_org, name_norm

_MAX_WORDS = 6
_CHUNK = 400  # SQLite parameter batch


def _windows(text: str) -> set[str]:
    words = name_norm(text).split()
    return {" ".join(words[i : i + n]) for n in range(1, _MAX_WORDS + 1) for i in range(len(words) - n + 1)}


def _lookup(ctx: CheckContext, sql: str, keys: list[str]) -> list:
    rows = []
    for i in range(0, len(keys), _CHUNK):
        part = keys[i : i + _CHUNK]
        rows += ctx.db.query(sql.format(marks=",".join("?" * len(part))), tuple(part))
    return rows


@register_checker
class NamesScan(BaseChecker):
    id, family = "names.scan", "registry"
    description = "Find firm or platform names from SEBI's debarred list and official caution notices in the message."
    consumes = frozenset({"message.text"})
    produces = frozenset({"DEBARRED_ENTITY", "ON_CAUTION_LIST"})
    needs = ("db",)
    source = "nse_debarred"
    cache_ttl_s = -1
    decisive = True

    async def check(self, entity: Entity, ctx: CheckContext):
        if ctx.db is None:
            return unknown("source_missing")
        windows = _windows(ctx.raw(entity))
        debarred = _lookup(
            ctx,
            "SELECT name, order_ref, order_date, period FROM debarred WHERE revoked = 0 AND name_norm IN ({marks})",
            sorted(w for w in windows if " " in w and len(w) >= 8),
        )
        debarred = [r for r in debarred if looks_like_org(r["name"])]
        caution = _lookup(
            ctx,
            "SELECT list_id, display, published_at, source_url FROM caution_entry "
            "WHERE entry_type = 'name' AND value_norm IN ({marks})",
            sorted(w for w in windows if len(w) >= 4),
        )
        codes, facts = [], {}
        if caution:
            codes.append("ON_CAUTION_LIST")
            facts["caution"] = [
                {"list_id": r["list_id"], "display": r["display"], "published_at": r["published_at"],
                 "source_url": r["source_url"]} for r in caution[:3]
            ]
        if debarred:
            codes.append("DEBARRED_ENTITY")
            facts["debarred"] = [
                {"name": r["name"], "order_ref": r["order_ref"], "order_date": r["order_date"], "period": r["period"]}
                for r in debarred[:3]
            ]
        if not codes:
            return clear()
        src_id = "caution_lists" if caution else "nse_debarred"
        return hit(*codes, basis="official_list", facts=facts, source=SourceRef(id=src_id, as_on=ctx.db.source_as_on(src_id)))
