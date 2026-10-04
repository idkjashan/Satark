"""ExtractorPipeline: regex extraction, QR, and the LLM/OCR glue (LLD §6.4-6.5, §8; CONTRACTS §4).

regex() is the fast deterministic pass: find every identifier, resolve overlaps and roles,
create entities (deduped, placeholders, masked), add the deterministic claims (brand
impersonation, registration-number-adjacent names), and set case.masked_text. llm()/merge()/
add_drafts() are thin delegations to extract/llm.py (kept in a separate file so this one stays
readable); ocr() delegates to extract/ocr.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from satark.harness.extract import llm as llm_mod
from satark.harness.extract import ocr as ocr_mod
from satark.harness.extract.fns import DERIVERS, VALIDATORS
from satark.harness.extract.match import (
    CompiledPattern,
    Match,
    compile_patterns,
    effective_class,
    find_matches,
    outermost_spans,
    resolve_role,
    splice_spans,
)
from satark.harness.extract.normalise import fold_pattern, normalise_text
from satark.harness.state import CaseState, Entity, EntityDraft, Origin
from satark.infra.norm import registrable_domain, sha256_hex

if TYPE_CHECKING:
    from satark.config import Config
    from satark.harness.models import ModelRouter
    from satark.infra.db import RegistryDB

Extraction = llm_mod.Extraction

_URL_EMBED_EXEMPT = {"tg.link", "social.handle", "app.package", "apk.link"}


# --------------------------------------------------------------------------------- small helpers


def _quote(text: str, start: int, end: int, pad: int = 50, cap: int = 120) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return text[s:e].strip()[:cap]


@dataclass
class _Cand:
    m: Match
    role: str
    cls: str
    valid: bool


def _build_candidates(text: str, config: Config, compiled: dict[str, list[CompiledPattern]]) -> list[_Cand]:
    types = [t for t, spec in config.entities.items() if spec.get("kind") == "identifier"]
    out = []
    for m in find_matches(text, config.entities, compiled, types=types):
        spec = config.entities[m.type]
        role = resolve_role(spec, text, m.start)
        cls = effective_class(spec, role)
        vfn = VALIDATORS.get(spec.get("validate")) if spec.get("validate") else None
        valid = bool(vfn(m.value)) if vfn else True
        out.append(_Cand(m=m, role=role, cls=cls, valid=valid))
    return out


def _exempt_overlap(a: Match, b: Match) -> bool:
    types = {a.type, b.type}
    return a.type != b.type and "url" in types and (types - {"url"}) <= _URL_EMBED_EXEMPT


def _worse(a: _Cand, b: _Cand) -> _Cand:
    """The candidate to drop when two different types overlap: keep U, then valid, then longer."""
    if (a.cls == "U") != (b.cls == "U"):
        return b if a.cls == "U" else a
    if a.valid != b.valid:
        return b if a.valid else a
    return b if (a.m.end - a.m.start) >= (b.m.end - b.m.start) else a


def _resolve_overlaps(cands: list[_Cand]) -> list[_Cand]:
    # ponytail: O(n^2) pairwise sweep; fine at the <=4,000-char / dozens-of-matches scale this
    # runs at, switch to a sorted-interval sweep if a pathological input makes this show up.
    dropped: set[int] = set()
    for i, a in enumerate(cands):
        if i in dropped:
            continue
        for j in range(i + 1, len(cands)):
            # same-type overlaps go through the same resolution too (e.g. money.inr's grouped-
            # comma pattern and its bare-number pattern both matching "₹1,00,000" / "₹1"):
            # the longer match wins, same as a cross-type conflict.
            if j in dropped or _exempt_overlap(a.m, cands[j].m):
                continue
            b = cands[j]
            if a.m.start >= b.m.end or b.m.start >= a.m.end:
                continue  # no overlap
            loser = _worse(a, b)
            dropped.add(i if loser is a else j)
            if loser is a:
                break
    return [c for idx, c in enumerate(cands) if idx not in dropped]


def _apply_max_per_case(cands: list[_Cand], config: Config) -> list[_Cand]:
    """Cap only public (P) values here. Every U, C and R value must still become an entity so it is
    masked; how many of them get CHECKED is capped by the planner (code review: a 4th OTP stayed in
    masked_text when the cap dropped it before masking)."""
    cands = sorted(cands, key=lambda c: c.m.start)
    counts: dict[str, int] = {}
    out = []
    for c in cands:
        spec = config.entities[c.m.type]
        cap = spec.get("max_per_case") if spec.get("class") == "P" else None
        n = counts.get(c.m.type, 0)
        if cap is not None and n >= cap:
            continue
        counts[c.m.type] = n + 1
        out.append(c)
    return out


# ------------------------------------------------------------------------------- name/claim rules

_TITLE_WORD = r"[A-Z][a-z]+"
_FIRM_SUFFIX = r"(?:Pvt\s?Ltd|Private\s+Limited|LLP|Ltd|Advisors?|Advisory|Research|Capital|Securities|Investments?|Wealth)"
_NAME_RUN = re.compile(rf"({_TITLE_WORD}(?:\s+{_TITLE_WORD}){{1,4}}(?:\s+{_FIRM_SUFFIX})?)")
# A company named in the message ("Lazard Asset Management India", "Brightcrest Wealthnova Capital Pvt Ltd"):
# 1-4 Title-Case words, then a business word, then an optional legal tail. No regex or model otherwise
# finds these, so the agent loop would have no name to look up on the web or in the SEBI register.
_ORG_WORD = r"(?:Pvt\.?\s?Ltd\.?|Private\s+Limited|Limited|LLP|Ltd\.?|Inc|Advisors?|Advisory|Advisers|Research|Capital|Securities|Investments?|Investors|Wealth|Asset\s+Management|Management|Finance|Financial|Fintech|Broking|Brokers|Traders|Trading|Markets|Fund|Funds|Holdings|Equities|Associates|Services)"
_ORG_NAME = re.compile(rf"(?<![A-Za-z])({_TITLE_WORD}(?:\s+{_TITLE_WORD}){{0,3}}(?:\s+{_ORG_WORD})+(?:\s+(?:India|Pvt\.?\s?Ltd\.?|Private\s+Limited|Limited|LLP|Ltd\.?))*)(?![A-Za-z])")
_NAME_STOP = {
    "sebi", "registered", "investment", "adviser", "advisor", "research", "analyst",
    "portfolio", "manager", "broker", "reg", "no", "regn", "regd", "ria", "the", "with",
    "as", "for", "and", "dear", "mr", "ms", "mrs",
}
_CATEGORY_HINTS = (
    (re.compile(r"(?i)research\s+analyst|\bRA\b"), "RA"),
    (re.compile(r"(?i)investment\s+adviser|\badvisor\b|\bIA\b|\bRIA\b"), "IA"),
    (re.compile(r"(?i)broker"), "BROKER"),
    (re.compile(r"(?i)portfolio\s+manager|\bPMS\b"), "PMS"),
)
_REGISTERED_NO_NUMBER = re.compile(
    fold_pattern(r"(?i)sebi\s*(?:registered|se\s*registered)|registered\s+with\s+sebi|sebi\s*रजिस्टर्ड")
)


def _trim_role_words(words: list[str]) -> list[str]:
    """Drop leading AND trailing stoplisted role/title words (SEBI Registered Investment
    Adviser Rajesh Sharma -> Rajesh Sharma; Suresh Mehta Investment Adviser -> Suresh Mehta),
    but never trim every word away."""
    i, j = 0, len(words)
    while i < j - 1 and words[i].lower() in _NAME_STOP:
        i += 1
    while j > i + 1 and words[j - 1].lower() in _NAME_STOP:
        j -= 1
    return words[i:j]


def _name_candidate(window: str) -> str | None:
    # ponytail: a naive Title-Case-run + stoplist heuristic, not a real NER (named-entity
    # recognition) model. Deliberately conservative (a missed name beats a wrong one, per
    # spec); upgrade path is the LLM extraction path, which already handles this better when on.
    matches = list(_NAME_RUN.finditer(window))
    if not matches:
        return None
    kept = _trim_role_words(matches[-1].group(1).split())
    return " ".join(kept) if len(kept) >= 2 else None


# "Hi, I'm Suresh Mehta, SEBI Registered Research Analyst, registration number INH...": the
# name can sit anywhere in the sentence that holds the number, introduced by a self-intro
# phrase rather than being immediately next to the number. The capture is 1-3 Title-Case words
# right after the intro phrase; a comma or an ALL-CAPS brand word (SEBI, RBI...) - which never
# matches _TITLE_WORD - naturally stops it before any role words that follow without one.
_SELF_INTRO = re.compile(
    rf"(?:\bi\s*'?\s*m\b|\bi\s+am\b|\bthis\s+is\b|मैं|\bmain\b)\s+({_TITLE_WORD}(?:\s+{_TITLE_WORD}){{0,2}})",
    re.I,
)
_SENTENCE_END = re.compile(r"[!?।\n]+|\.(?=\s|$)")
# "Reg. No. INH000000081", "Mr. Sharma", "XYZ Pvt. Ltd." are not sentence ends
_ABBREVIATION = re.compile(r"(?i)\b(?:reg|regn|regd|no|nos|mr|mrs|ms|dr|pvt|ltd|co|sr|jr|st|vs|inc)$")


def _boundaries(text: str, lo: int, hi: int):
    for m in _SENTENCE_END.finditer(text, lo, hi):
        if m.group(0) == "." and _ABBREVIATION.search(text, max(0, m.start() - 6), m.start()):
            continue
        yield m


def _self_intro_name(sentence: str) -> str | None:
    m = _SELF_INTRO.search(sentence)
    if not m:
        return None
    kept = _trim_role_words(m.group(1).split())
    return " ".join(kept) if len(kept) >= 2 else None


def _sentence_around(text: str, pos: int) -> str:
    start = max((m.end() for m in _boundaries(text, 0, pos)), default=0)
    end_m = next(_boundaries(text, pos, len(text)), None)
    return text[start : end_m.start() if end_m else len(text)]


def _category_hint(around: str, fallback: str) -> str:
    for pat, cat in _CATEGORY_HINTS:
        if pat.search(around):
            return cat
    return fallback


# A brand *mention* ("Zerodha is SEBI registered", "check on SEBI's website") is not an
# impersonation claim: only the message presenting itself as FROM / acting for the brand is.
# {A} is the escaped (and nukta-folded) alias, substituted per brand below. \b breaks right
# after a Devanagari word ending in a dependent vowel sign (a matra is not \w to Python's re),
# so boundaries touching {A} use lookarounds over the whole Devanagari block instead of \b;
# plain \b is fine for the pure-ASCII trigger words (from, official, notice...).
_WB_BEFORE = r"(?<![\wऀ-ॿ])"
_WB_AFTER = r"(?![\wऀ-ॿ])"
_IMPERSONATION_TRIGGERS = [
    r"\bfrom\s+{A}" + _WB_AFTER,
    _WB_BEFORE + r"{A}(?:\s+\w+){{0,3}}\s+(?:notice|official|officer)\b",  # "SEBI ... Notice", <=3 filler words
    r"\bofficial\s+{A}" + _WB_AFTER,  # "Official SEBI"
    r"\bon\s+behalf\s+of\s+{A}" + _WB_AFTER,
    _WB_BEFORE + r"{A}\s+(?:customer\s+care|customer\s+support|support\s+team|support)\b",
    _WB_BEFORE + r"{A}\s+ki\s+taraf\s+se\b",
    r"{A}\s*की\s*ओर\s*से",
    r"(?m)^\s*{A}\s*$",  # the brand name alone on its own line: a forwarded message's header
    r"(?mi)^\s*(?:from|sender)\s*[:\-]\s*{A}" + _WB_AFTER,
]


def _compile_impersonation_patterns(brands: list[dict[str, Any]]) -> list[tuple[dict[str, Any], re.Pattern]]:
    """Every (brand, compiled trigger) pair, built once: folding + escaping + compiling ~120
    aliases x 9 triggers on every regex() call measured at ~60ms, well over the <10ms budget."""
    out: list[tuple[dict[str, Any], re.Pattern]] = []
    for brand in brands:
        for alias in brand.get("aliases", []):
            esc = re.escape(fold_pattern(alias))
            for tmpl in _IMPERSONATION_TRIGGERS:
                out.append((brand, re.compile(tmpl.format(A=esc), re.I)))
    return out


class ExtractorPipeline:
    def __init__(self, config: Config, router: ModelRouter | None = None, db: RegistryDB | None = None):
        self.config = config
        self.router = router
        self.db = db
        self._compiled = compile_patterns(config.entities)
        self._impersonation_patterns = _compile_impersonation_patterns(config.brands)

    # ------------------------------------------------------------------------------------ entities

    def _get_or_create(
        self, case: CaseState, type_: str, cls: str, value: str, display: str, role: str,
        origin: Origin, attrs: dict[str, Any], valid: bool = True,
    ) -> tuple[Entity, bool]:
        norm_hash = sha256_hex(f"{case.case_id}:{value}") if value else ""
        if norm_hash:
            existing = next((e for e in case.entities if e.type == type_ and e.norm_hash == norm_hash), None)
            if existing:
                return existing, False
        spec = self.config.entities[type_]
        placeholder = ""
        prefix = spec.get("placeholder")
        if prefix:
            case.next_id(prefix)
            placeholder = f"[{prefix}_{case.counters[prefix]}]"
        ent = Entity(
            id=case.next_id("e"), type=type_, cls=cls, placeholder=placeholder, norm_hash=norm_hash,
            value=SecretStr(value if cls != "U" else ""), display=(display if cls != "U" else ""),
            role=role, origin=origin, attrs=attrs or {}, valid=valid,
        )
        case.entities.append(ent)
        return ent, True

    def _new_claim(
        self, case: CaseState, type_: str, attrs: dict[str, Any], refs: list[str], quote: str, origin: Origin
    ) -> Entity | None:
        dup = next(
            (e for e in case.entities if e.type == type_ and e.refs == refs and e.attrs == attrs), None
        )
        if dup:
            return None
        spec = self.config.entities[type_]
        ent = Entity(id=case.next_id("e"), type=type_, cls=spec["class"], attrs=attrs, refs=refs, quote=quote, origin=origin)
        case.entities.append(ent)
        return ent

    # -------------------------------------------------------------------------------------- claims

    def _impersonation_claims(self, case: CaseState, text: str, masked_preview: str) -> list[Entity]:
        new: list[Entity] = []
        seen: set[str] = set()
        for brand, pat in self._impersonation_patterns:
            if brand["id"] in seen:
                continue
            m = pat.search(text)
            if m is None:
                continue
            seen.add(brand["id"])
            attrs = {"org": brand["name"], "kind": brand["kind"], "brand_id": brand["id"]}
            ent = self._new_claim(case, "claim.impersonates", attrs, [], _quote(masked_preview, m.start(), m.end()), "regex")
            if ent:
                new.append(ent)
        return new

    def _name_and_party(self, case: CaseState, before: str, after: str, sentence: str) -> tuple[str | None, list[Entity]]:
        """The near-number/phrase window first, then anywhere-in-sentence self-introductions
        ("I'm X", "मैं X", ...). Returns the party.name entity id (or None) and any new entity."""
        name = _name_candidate(before) or _name_candidate(after) or _self_intro_name(sentence)
        if not name:
            return None, []
        party, created = self._get_or_create(case, "party.name", "C", name.lower(), name, "unknown", "regex", {"kind": "person"})
        return party.id, ([party] if created else [])

    def _org_names(self, text: str) -> list[tuple[str, int, int]]:
        """(name, start, end) of company-like names that are not a brand Satark already knows (those have official
        domains and lists; a web search for them adds noise). At most 2 per message."""
        known = {a.casefold() for b in self.config.brands for a in b.get("aliases", [])}
        out = []
        for m in _ORG_NAME.finditer(text):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .")
            if not re.fullmatch(_ORG_WORD, name.split()[0]) and not {w.casefold() for w in name.split()} & _NAME_STOP and name.casefold() not in known and not any(k in name.casefold() for k in known if len(k) > 4):
                out.append((name, m.start(1), m.start(1) + len(m.group(1).rstrip(" ."))))
        return out[:2]

    def _registration_claims(self, case: CaseState, text: str, masked_preview: str, reg_cands: list[_Cand]) -> list[Entity]:
        new: list[Entity] = []
        for c in reg_cands:
            reg_ent = next((e for e in case.entities if e.type == "sebi.reg_no" and e.norm_hash == sha256_hex(f"{case.case_id}:{c.m.value}")), None)
            if reg_ent is None:
                continue
            before = text[max(0, c.m.start - 60) : c.m.start]
            after = text[c.m.end : c.m.end + 30]
            sentence = _sentence_around(text, c.m.start)
            party_id, created = self._name_and_party(case, before, after, sentence)
            new += created
            refs = [reg_ent.id] if party_id is None else [party_id, reg_ent.id]
            category = _category_hint(before + after, DERIVERS["reg_category"](c.m.value)["category"])
            claim = self._new_claim(
                case, "claim.registered_as", {"regulator": "SEBI", "category": category},
                refs, _quote(masked_preview, c.m.start, c.m.end), "regex",
            )
            if claim:
                new.append(claim)
        if not reg_cands:
            for m in _REGISTERED_NO_NUMBER.finditer(text):
                before = text[max(0, m.start() - 60) : m.start()]
                after = text[m.end() : m.end() + 60]
                sentence = _sentence_around(text, m.start())
                party_id, created = self._name_and_party(case, before, after, sentence)
                new += created
                refs = [] if party_id is None else [party_id]
                category = _category_hint(before + after, "OTHER")
                claim = self._new_claim(
                    case, "claim.registered_as", {"regulator": "SEBI", "category": category},
                    refs, _quote(masked_preview, m.start(), m.end()), "regex",
                )
                if claim:
                    new.append(claim)
        return new

    # --------------------------------------------------------------------------------------- regex

    def regex(self, case: CaseState, text: str, claims: bool = True, as_message: bool = True) -> list[Entity]:
        """`claims=False`: identifiers, masking and message.text only - skip the deterministic
        claim.*/party.name heuristics. The orchestrator passes False once the `extract` LLM role
        is on, since the model then does that semantic work (is this a claim? who is the
        adviser?) directly, and deterministic + model claims for the same mention would double up.
        `as_message=False` (chat turns): identifiers only; the case's checked message stays as it was."""
        text = normalise_text(text)
        new_entities: list[Entity] = []
        u_spans: list[tuple[int, int, str]] = []
        mask_spans: list[tuple[int, int, str]] = []

        cands = _apply_max_per_case(_resolve_overlaps(_build_candidates(text, self.config, self._compiled)), self.config)
        cands.sort(key=lambda c: c.m.start)

        for c in cands:
            spec = self.config.entities[c.m.type]
            ent, created = self._get_or_create(case, c.m.type, c.cls, c.m.value, c.m.text, c.role, "regex", dict(c.m.attrs), c.valid)
            if created:
                new_entities.append(ent)
                for name in spec.get("derive") or []:
                    fn = DERIVERS.get(name)
                    if fn:
                        ent.attrs.update(fn(c.m.value))
            if ent.placeholder:
                if ent.cls == "U":
                    u_spans.append((c.m.start, c.m.end, ent.placeholder))
                mask_spans.append((c.m.start, c.m.end, ent.placeholder))

        for c in cands:
            spec = self.config.entities[c.m.type]
            if "entity:domain" in (spec.get("derive") or []):
                dom = registrable_domain(c.m.value)
                dom_spec = self.config.entities["domain"]
                dent, created = self._get_or_create(case, "domain", dom_spec["class"], dom, dom, "unknown", "derived", {})
                if created:
                    new_entities.append(dent)

        if not as_message:
            return new_entities
        for name, start, end in self._org_names(text):  # also when the model extracts: a 4B model misses most of them
            ent, created = self._get_or_create(case, "party.name", "C", name.lower(), name, "unknown", "regex", {"kind": "org"})
            if created:
                new_entities.append(ent)
            if ent.placeholder:
                mask_spans.append((start, end, ent.placeholder))
        masked_preview = splice_spans(text, outermost_spans(mask_spans))
        case.masked_text = masked_preview
        if claims:
            reg_cands = [c for c in cands if c.m.type == "sebi.reg_no"]
            new_entities += self._registration_claims(case, text, masked_preview, reg_cands)
            new_entities += self._impersonation_claims(case, text, masked_preview)

        msg_value = splice_spans(text, outermost_spans(u_spans))
        existing_msg = case.by_type("message.text")
        if existing_msg:
            existing_msg[0].value = SecretStr(msg_value)
            existing_msg[0].display = msg_value
        else:
            msg_ent = Entity(id=case.next_id("e"), type="message.text", cls="C", value=SecretStr(msg_value), display=msg_value, origin="regex")
            case.entities.append(msg_ent)
            new_entities.append(msg_ent)

        return new_entities

    # ------------------------------------------------------------------------------------------ qr

    def qr(self, case: CaseState, payload: str) -> list[Entity]:
        if re.match(r"(?i)^upi://pay\?", payload.strip()):
            ent, created = self._get_or_create(case, "upi.uri", "C", payload.strip(), payload.strip(), "unknown", "qr", {})
            return [ent] if created else []
        return self.regex(case, payload)

    # --------------------------------------------------------------------------- LLM / OCR / merge

    async def ocr(self, image: bytes, mime: str) -> str | None:
        return await ocr_mod.run(image, mime)

    async def llm(self, case: CaseState, image: bytes | None = None, image_mime: str | None = None) -> Extraction | None:
        return await llm_mod.extract(case, self.config, self.router, image, image_mime)

    def merge(self, case: CaseState, extraction: Extraction | None) -> list[Entity]:
        return llm_mod.merge(self, case, extraction)

    def add_drafts(self, case: CaseState, drafts: list[EntityDraft], origin: Origin = "derived") -> list[Entity]:
        return llm_mod.add_drafts(self, case, drafts, origin)
