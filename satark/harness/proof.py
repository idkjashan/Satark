"""Proof for the checklist: what was checked, against which source, what came back, and where the user can verify it.

Built from the evidence a checker already has (no new lookups), in the request's language. It goes only to the
user's own event stream, never into a model prompt: `checked` is the identifier as the user wrote it. A row may
read as a pass only when the check ran: unknown, error and skipped results carry `outcome: "unknown"` and a `why`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import quote

_URL_LINE = re.compile(r"^\d+\.\s*(.*?)\s+-\s+.*?\((https?://\S+?)\)\s*$")
_WHY = {"offline", "timeout", "source_missing", "blocked", "budget", "unmet_dependency", "checker_error", "contract",
        "rdap_error", "unparseable", "safe_browsing_error", "disabled"}


def _why(config, lang: str, reason: str | None) -> str:
    r = (reason or "").strip()
    key = r if r in _WHY else ("http_error" if r.startswith("http_") else "other")
    return config.t(lang, f"proof.why.{key}")


def check_proof(ev, case, config, lang: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    t = lambda k, **kw: config.t(lang, k, **kw)  # noqa: E731
    ents = [e for i in ev.entity_ids if (e := case.entity(i))]
    shown = [e.display for e in ents if e.type != "message.text" and e.display and e.cls != "U"]
    checked = ", ".join(dict.fromkeys(shown)) or t("proof.the_message")
    spec = config.sources.get(ev.source.id) or {}
    src_name = spec.get("name") or t("proof.own_rules")
    live = spec.get("kind") == "live"
    facts = ev.facts or {}
    value = quote((shown[0] if shown else "").removeprefix("https://").removeprefix("http://").split("/")[0]
                  if ev.checker_id.startswith("link.") else (shown[0] if shown else ""), safe="")
    if ev.checker_id.startswith("app."):
        value = quote(shown[0] if shown else "", safe="")
    url = (facts.get("source_url") or (spec.get("verify_url") or "").replace("{value}", value)) or None
    if ev.source.id == "sebi_registers" and shown:
        reg = shown[0].upper()
        url = ("https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=14" if reg.startswith("INH")
               else url if reg.startswith("INA") else "https://www.sebi.gov.in/intermediaries.html")
    out = {"checked": checked, "source_name": src_name, "url": url}
    out.update({"live": True, "fetched_at": now.isoformat(timespec="seconds")} if live else {"as_on": ev.source.as_on})
    if ev.status not in ("hit", "clear"):
        out.update(outcome="unknown", result=t("proof.not_checked"), why=_why(config, lang, ev.reason))
        return out
    sigs = [s.code for s in ev.signals]
    assure = any(config.signal(c).get("polarity") == "assurance" for c in sigs)
    out["outcome"] = "warning" if ev.status == "hit" else ("found" if assure else "clear")
    if ev.status == "clear" and facts.get("registered_name") and ev.checker_id.startswith("sebi.reg"):
        reg = facts.get("reg_no") or (shown[0] if shown else "")
        extra = f", {t('proof.valid_till', date=facts['valid_to'])}" if facts.get("valid_to") not in (None, "") else ""
        out["result"] = t("proof.reg_found", name=facts["registered_name"], reg=reg, category=facts.get("category", "")) + extra
    elif "age_days" in facts:
        out["result"] = t("proof.domain_age", days=facts["age_days"], date=str(facts.get("registered_on", ""))[:10])
    elif facts.get("rdap_not_found"):
        out["result"] = t("proof.domain_not_registered")
    elif sigs:
        out["result"] = " ".join(t(f"signal.{c}") for c in sigs[:3])
    else:
        out["result"] = t("proof.nothing_found", source=src_name) + (
            f" ({t('proof.data_as_on', date=ev.source.as_on)})" if ev.source.as_on else "")
    return out


def tool_proof(tool: str, label: str, ok: bool, text: str, config, lang: str, now: datetime | None = None) -> dict:
    """The same shape for an agent lookup: a web search lists its hits (title and url), a register search its answer."""
    t = lambda k, **kw: config.t(lang, k, **kw)  # noqa: E731
    now = now or datetime.now(UTC)
    web = tool.endswith("search") and not tool.startswith("satark.")
    items = [{"title": m.group(1)[:100], "url": m.group(2)} for ln in (text or "").splitlines() if (m := _URL_LINE.match(ln))]
    out: dict = {"checked": label, "source_name": t("proof.web_search") if web else t("proof.own_rules"),
                 "url": items[0]["url"] if items else None}
    if web:
        out.update(live=True, fetched_at=now.isoformat(timespec="seconds"), items=items[:5])
    if not ok or (web and not items):
        reason = "timeout" if "timed out" in (text or "") else ("other" if ok is False else "no_results")
        out.update(outcome="unknown" if not ok else "clear", result=t("proof.not_checked") if not ok else t("proof.no_reports"),
                   why=t(f"proof.why.{reason}") if not ok else None)
        return out
    out["outcome"] = "clear" if (text or "").startswith("found in SEBI register: no") else "found"
    out["result"] = t("proof.search_found", n=len(items)) if web else (text or "").splitlines()[0][:200]
    return out


def check_item(ev, case, config) -> dict:
    """The `check_result` event payload: the checker's outcome plus its proof."""
    return {
        "step_id": ev.step_id, "checker_id": ev.checker_id, "family": ev.family, "status": ev.status,
        "signals": [s.code for s in ev.signals], "source": {"id": ev.source.id, "as_on": ev.source.as_on},
        "stale": ev.stale, "cached": ev.cached, "proof": check_proof(ev, case, config, case.lang),
    }
