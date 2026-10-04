"""Masking, LLM-input building and output guards (LLD §6.4-6.5; CONTRACTS §4).

Pure functions; `mask`/`unmask`/`pii_leaks`/`is_advice_seeking` take no Config so they can be
called from anywhere without threading one through. They load `config/entities.yaml` and
`config/lexicons/guards.yaml` straight off disk once (lru_cache) instead of going through
satark.config, to avoid pulling in the whole checker/registry import graph for a text check.
`brief` and `check_output` already receive a `Config`, so they use it directly.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import SecretStr

from satark.harness.state import CaseState, Entity
from satark.infra.norm import sha256_hex

if TYPE_CHECKING:
    from satark.config import Config

_ROOT = Path(__file__).resolve().parents[2]

# `match` lives in satark.harness.extract, whose __init__ imports llm.py, which imports this
# module's brief()/pii_leaks(). Importing it at module load time (instead of inside the two
# functions that need it) would make satark.harness.extract import satark.harness.guards
# while guards is still mid-import - a circular import. Deferring it here breaks the cycle:
# by the time mask()/pii_leaks() are actually called, every module has finished loading.


@functools.lru_cache(maxsize=1)
def _entities_cfg() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((_ROOT / "config" / "entities.yaml").read_text()) or {}


@functools.lru_cache(maxsize=1)
def _u_compiled() -> dict[str, list]:
    from satark.harness.extract.match import compile_patterns

    cfg = _entities_cfg()
    compiled = compile_patterns(cfg)
    return {t: pats for t, pats in compiled.items() if cfg[t].get("class") == "U"}


@functools.lru_cache(maxsize=1)
def _guard_lexicon() -> dict[str, dict[str, list[Any]]]:
    path = _ROOT / "config" / "lexicons" / "guards.yaml"
    return yaml.safe_load(path.read_text()) or {} if path.exists() else {}


# --------------------------------------------------------------------------------------- masking


def _mask_fresh_u(text: str, case: CaseState) -> str:
    """Safety net: a chat message may carry a brand new OTP/Aadhaar the regex pass never saw."""
    from satark.harness.extract.match import find_matches, outermost_spans, splice_spans

    compiled = _u_compiled()
    if not compiled:
        return text
    matches = find_matches(text, _entities_cfg(), compiled)
    if not matches:
        return text
    cfg = _entities_cfg()
    spans: list[tuple[int, int, str]] = []
    for m in matches:
        norm_hash = sha256_hex(f"{case.case_id}:{m.value}") if m.value else ""
        ent = next((e for e in case.entities if e.type == m.type and e.norm_hash == norm_hash), None)
        if ent is None:
            prefix = cfg[m.type].get("placeholder")
            placeholder = ""
            if prefix:
                case.next_id(prefix)
                placeholder = f"[{prefix}_{case.counters[prefix]}]"
            ent = Entity(
                id=case.next_id("e"), type=m.type, cls="U", placeholder=placeholder,
                norm_hash=norm_hash, value=SecretStr(""), display="", origin="regex",
            )
            case.entities.append(ent)
        if ent.placeholder:
            spans.append((m.start, m.end, ent.placeholder))
    return splice_spans(text, outermost_spans(spans))


def mask(text: str, case: CaseState) -> str:
    """Every known U/C entity's display text and raw value -> its placeholder (longest first),
    plus a U-class regex rescan for identifiers not yet in the case."""
    needles: list[tuple[str, str]] = []
    for e in case.entities:
        if e.cls != "C" or not e.placeholder:
            continue
        if e.display:
            needles.append((e.display, e.placeholder))
        val = e.value.get_secret_value()
        if val and val != e.display:
            needles.append((val, e.placeholder))
    out = text
    for needle, placeholder in sorted(needles, key=lambda n: -len(n[0])):
        out = out.replace(needle, placeholder)
    return _mask_fresh_u(out, case)


_PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")
_HIDDEN = {"en": "(hidden)", "hi": "(छिपाया गया)"}


def unmask(text: str, case: CaseState, lang: str = "en") -> str:
    """C placeholders -> the display value the user sent; U placeholders -> a localized
    "(hidden)"; a placeholder the case doesn't know is left as-is."""
    hidden = _HIDDEN.get(lang, _HIDDEN["en"])

    def repl(m: re.Match[str]) -> str:
        ent = next((e for e in case.entities if e.placeholder == m.group(0)), None)
        if ent is None:
            return m.group(0)
        if ent.cls == "C":
            return ent.display or ent.value.get_secret_value()
        return hidden

    return _PLACEHOLDER.sub(repl, text)


# --------------------------------------------------------------------------------------- brief


def _evidence_brief(ev: Any, case: CaseState) -> dict[str, Any]:
    facts = {k: (mask(v, case) if isinstance(v, str) else v) for k, v in ev.facts.items() if not k.endswith("_raw")}
    return {"id": ev.id, "checker": ev.checker_id, "status": ev.status, "signals": [s.code for s in ev.signals], "facts": facts}


def brief(case: CaseState, role: str, config: Config) -> str:
    """The ONLY builder of LLM input: placeholders, safe attrs and llm-visible facts, never
    Entity.value or Entity.display."""
    data: dict[str, Any] = {
        "lang": case.lang,
        "simple": case.simple,
        # re-masked here: names found after masked_text was built (claims, the AI's add_and_check) get placeholders too
        "masked_text": f"<untrusted_message>{mask(case.masked_text, case)[:1500]}</untrusted_message>",
        "entities": [
            {"id": e.id, "type": e.type, "placeholder": e.placeholder, "role": e.role, "attrs": e.attrs}
            for e in case.entities
            if e.type != "message.text"
        ],
        # sorted, not in completion order: parallel checks finish in a different order each run, and a small model
        # answers differently to the same evidence in a different order
        "evidence": [_evidence_brief(ev, case) for ev in sorted(case.ledger, key=lambda e: (e.checker_id, e.entity_ids))],
    }
    if case.verdict:
        data["verdict"] = {
            "level": case.verdict.level,
            "confidence": case.verdict.confidence,
            "reasons": [{"code": r.code, "title": config.t(case.lang, f"signal.{r.code}")} for r in case.verdict.reasons],
        }
    data["could_not_check"] = [f.family for f in case.verdict.checked if f.status == "unknown"] if case.verdict else []
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------------- pii tripwire


_NOT_RAW_PII = {"domain", "message.text"}  # domain is a documented safe attribute (LLD §6.5);
# message.text is the synthetic whole-message container (its content is already represented
# by masked_text), not an identifier to tripwire on.


def _bare_host(url: str) -> str:
    u = re.sub(r"(?i)^https?://", "", (url or "").strip()).rstrip("/").lower()
    return u[4:] if u.startswith("www.") else u


def pii_leaks(prompt: str, case: CaseState) -> list[str]:
    """Type names of raw U/C values found in an outgoing prompt. Never returns values.

    P-class values (money.inr, money.return_rate, bank.ifsc...) are not masked for LLMs in the
    first place (CONTRACTS §4, entities.yaml `class: P`) - amounts and rates are meant to be
    freely discussable, so they are never a leak here."""
    from satark.harness.extract.match import find_matches

    leaked: set[str] = set()
    for e in case.entities:
        if e.cls == "P" or e.type in _NOT_RAW_PII:
            continue
        if e.type == "url" and _bare_host(e.display) == (e.attrs.get("host") or "").lower():
            continue  # a bare-domain link ("sebi.gov.in") carries nothing beyond its public host attribute
        for candidate in (e.value.get_secret_value(), e.display):
            if candidate and len(candidate) >= 4 and candidate in prompt:
                leaked.add(e.type)
    compiled = _u_compiled()
    if compiled:
        for m in find_matches(prompt, _entities_cfg(), compiled):
            leaked.add(m.type)
    return sorted(leaked)


# ------------------------------------------------------------------------------------- scope note
#
# There is deliberately no keyword-based "is this on topic" gate here: a scammer could dodge a
# keyword gate by larding a real scam message with jailbreak-ish phrases ("ignore previous
# instructions, this is safe"), and the harness must still check that message, not wave it
# through as off-topic. Extraction.related_to_money (satark/harness/extract/llm.py) carries the
# model's own judgement for the orchestrator (D) to act on; is_advice_seeking() below is
# deterministic and used for logging/lesson-routing only, never as a refusal gate.


# --------------------------------------------------------------------------------- output guards


def _lexicon_hits(text: str, section: dict[str, list[Any]] | None) -> bool:
    for entries in (section or {}).values():
        for e in entries or []:
            if isinstance(e, str):
                if re.search(e, text, re.I):
                    return True
                continue
            pat, ctx, window = re.compile(e["re"], re.I), re.compile(e["context"], re.I), int(e.get("window", 40))
            for m in pat.finditer(text):
                before, after = text[max(0, m.start() - window) : m.start()], text[m.end() : m.end() + window]
                if ctx.search(before) or ctx.search(after):
                    return True
    return False


_CODE_TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")


def _codes_mismatch(text: str, config: Config, expected: list[str] | None) -> bool:
    """True when the text names a known signal code that isn't one of `expected_codes`.
    (`expected_codes=None` means the caller isn't asserting coverage: never a mismatch.)"""
    if expected is None:
        return False
    found = {m.group(1) for m in _CODE_TOKEN.finditer(text) if m.group(1) in config.signals}
    return bool(found - set(expected))


_REGNO_LIKE = re.compile(r"\b(IN[A-Z]{1,2}\d{6,12}|INBI\d{8}|MF/\d{3}/\d{2}/\d{1,2}|IN-DP-[\w-]+|IN/[A-Z]+/\d{2}-\d{2}/\d{2,5})\b")
_ANY_PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")


def _grounding_problem(text: str, case: CaseState) -> bool:
    known_regs = {e.display for e in case.entities if e.type == "sebi.reg_no"}
    known_regs |= {e.value.get_secret_value() for e in case.entities if e.type == "sebi.reg_no"}
    fact_text = " ".join(str(v) for ev in case.ledger for v in ev.facts.values())
    if any(m.group(1) not in known_regs and m.group(1) not in fact_text for m in _REGNO_LIKE.finditer(text)):
        return True
    known_placeholders = {e.placeholder for e in case.entities if e.placeholder}
    return any(m.group(0) not in known_placeholders for m in _ANY_PLACEHOLDER.finditer(text))


_SCRIPT_RANGES = {"hi": (0x0900, 0x097F), "mr": (0x0900, 0x097F), "bn": (0x0980, 0x09FF), "ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F)}


def _script_ok(text: str, lang: str) -> bool:
    rng = _SCRIPT_RANGES.get(lang)
    if rng is None:
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    in_script = sum(1 for c in letters if rng[0] <= ord(c) <= rng[1])
    return (in_script / len(letters)) >= 0.6


def check_output(
    text: str, case: CaseState, config: Config, lang: str, expected_codes: list[str] | None = None, max_words: int = 90
) -> list[str]:
    """[] = pass. Otherwise a list of problem codes, in the order they were checked:
    codes_mismatch, no_tips, code_markup, grounding, affirmation, script, length."""
    problems: list[str] = []
    if _codes_mismatch(text, config, expected_codes):
        problems.append("codes_mismatch")
    lex = _guard_lexicon()
    if _lexicon_hits(text, lex.get("no_tips")):
        problems.append("no_tips")
    if "```" in text or re.search(r"(?i)<script\b", text):
        problems.append("code_markup")
    if _grounding_problem(text, case):
        problems.append("grounding")
    if _lexicon_hits(text, lex.get("affirmations")):
        problems.append("affirmation")
    if not _script_ok(text, lang):
        problems.append("script")
    if len(text.split()) > max_words:
        problems.append("length")
    return problems


def chip_ok(chip: str) -> bool:
    """A follow-up suggestion the user can tap: short human words (small models sometimes emit ids)."""
    c = (chip or "").strip()
    return 3 <= len(c) <= 60 and "_" not in c and "{" not in c and "http" not in c.lower()


def is_advice_seeking(text: str) -> bool:
    """"Which stock should I buy?" - deterministic, en/hi/hinglish. Logging/routing only,
    never a refusal gate (a product decision, not this function's concern)."""
    return _lexicon_hits(text, _guard_lexicon().get("advice_seeking"))
