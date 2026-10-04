"""Complaint-draft template for `POST /v1/report-draft` (CONTRACTS §6, §7.1; LLD §12.5).

Template-based, no LLM. `content/i18n/*.json` is expected to carry `report.*` keys
(placeholders in `{braces}`); until that content lands (or for a language it is missing
from), we fall back to English, then to the built-in English default below, so the
endpoint works end to end today.
"""

from __future__ import annotations

from typing import Any

from satark.config import Config
from satark.harness.state import CaseState

_DEFAULTS: dict[str, str] = {
    "report.heading": "Complaint details",
    "report.scam_type_line": "Type of scam: {scam_type}",
    "report.scam_type_unknown": "suspicious investment activity",
    "report.when": "When it happened: {when}",
    "report.how_paid": "How I paid: {how_paid}",
    "report.amount_band": "Amount involved: {amount_band}",
    "report.involved_header": "People, accounts or links involved:",
    "report.involved_row": "- {label}: {value}",
    "report.reasons_header": "Why I believe this is a scam:",
    "report.reason_row": "- {title}",
    "report.closing": "I would like this matter investigated and action taken against those responsible.",
}

# Context in which each portal (content/portals.json) is added, beyond ncrp_1930 (always first).
_PUMP_AND_TIPS_SCAM_TYPE = "T5"  # LLD §9.10, Appendix C: pump-and-dump "operator" channels
_PONZI_SCAM_TYPE = "T11"  # Appendix C: Ponzi / "guaranteed return" / deposit schemes
_PHONE_SMS_ENTITY_TYPES = ("phone", "sms.header")


def _t(config: Config, lang: str, key: str, **fmt: Any) -> str:
    text = config.i18n.get(lang, {}).get(key) or config.i18n.get("en", {}).get(key) or _DEFAULTS.get(key, key)
    return text.format(**fmt) if fmt else text


def _evidence(case: CaseState, config: Config, lang: str) -> list[dict[str, str]]:
    """Counterparty (C-class) identifiers only — UPI IDs, phone numbers, URLs, app ids, claimed
    registration numbers... Never a U-class value (CONTRACTS §6): those are masked and discarded
    at extraction, so `display` is already "" for them, but we also gate on `cls` explicitly."""
    return [
        {"label": config.t(lang, f"entity.{e.type}"), "value": e.display}
        for e in case.entities
        if e.cls == "C" and e.type != "message.text" and e.display
    ]


def _portals(case: CaseState, config: Config, lang: str) -> list[dict[str, Any]]:
    portals_cfg = config.portals.get("portals", {})
    verdict = case.verdict
    ids = ["ncrp_1930"]
    if verdict is not None:
        if "REG_FOUND" in verdict.assurances:
            ids.append("sebi_scores")  # loss involving a registered entity (LLD §9.10)
        if verdict.scam_type == _PUMP_AND_TIPS_SCAM_TYPE:
            ids.append("sebi_mi")
        if verdict.scam_type == _PONZI_SCAM_TYPE:
            ids.append("rbi_sachet")
    if any(e.cls == "C" and e.type in _PHONE_SMS_ENTITY_TYPES for e in case.entities):
        ids.append("chakshu")

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pid in ids:
        if pid in seen or pid not in portals_cfg:
            continue
        seen.add(pid)
        spec = portals_cfg[pid]
        row: dict[str, Any] = {"id": pid, "name": config.t(lang, f"portal.{pid}"), "url": spec.get("url", "")}
        if spec.get("phone"):
            row["phone"] = spec["phone"]
        out.append(row)
    return out


def draft_report(case: CaseState, config: Config, lang: str, answers: dict[str, Any] | None = None) -> dict[str, Any]:
    answers = answers or {}
    verdict = case.verdict
    scam_key = f"scam_type.{verdict.scam_type}" if verdict and verdict.scam_type else None

    def build(language: str) -> str:
        scam_name = config.t(language, scam_key) if scam_key else _t(config, language, "report.scam_type_unknown")
        lines = [
            _t(config, language, "report.heading"),
            "",
            _t(config, language, "report.scam_type_line", scam_type=scam_name),
        ]
        for field, key in (("when", "report.when"), ("how_paid", "report.how_paid"), ("amount_band", "report.amount_band")):
            if answers.get(field):
                lines.append(_t(config, language, key, **{field: answers[field]}))
        rows = _evidence(case, config, language)
        if rows:
            lines += ["", _t(config, language, "report.involved_header")]
            lines += [_t(config, language, "report.involved_row", label=r["label"], value=r["value"]) for r in rows]
        titles = [config.t(language, f"signal.{r.code}") for r in (verdict.reasons if verdict else [])]
        if titles:
            lines += ["", _t(config, language, "report.reasons_header")]
            lines += [_t(config, language, "report.reason_row", title=title) for title in titles]
        lines += ["", _t(config, language, "report.closing")]
        return "\n".join(lines)

    return {
        "text_en": build("en"),
        "text_lang": build(lang),
        "evidence": _evidence(case, config, lang),
        "portals": _portals(case, config, lang),
    }
