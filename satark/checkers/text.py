"""Text family checkers (LLD §9.8): red-flag phrase lexicon, impossible-return maths, claim-type
to signal mapping, and fake-regulator-notice email checks. See satark/checkers/base.py for the
plugin contract.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from satark.checkers.base import BaseChecker, CheckContext, clear, hit, register_checker, unknown
from satark.harness.state import CaseState, CheckResult, Entity
from satark.infra.norm import registrable_domain

# Devanagari combining vowel signs are not \w to Python's `re`, so \b on a single consonant
# (न, मत) is unreliable: it also fires inside unrelated syllables such as निवेश. Negators are
# matched as whole whitespace/punctuation-delimited tokens for Hindi; \b is fine for ASCII.
_ASCII_NEGATORS = re.compile(r"(?i)\b(never|don'?t|do not|avoid|beware|nahi|nahin|mat)\b")
_HI_NEGATOR_TOKENS = frozenset({"न", "मत", "नहीं", "नही"})
_TOKEN_SPLIT = re.compile(r"[\s,।!?.]+")
_NEGATION_WINDOW = 25


def _has_negator(span: str) -> bool:
    if _ASCII_NEGATORS.search(span):
        return True
    return any(t in _HI_NEGATOR_TOKENS for t in _TOKEN_SPLIT.split(span))


def _message_text(case: CaseState) -> str:
    msgs = case.by_type("message.text")
    return msgs[0].value.get_secret_value() if msgs else ""


def _is_official(db, domain: str) -> bool:
    return db is not None and db.one("SELECT 1 FROM official_domain WHERE domain = ?", (domain,)) is not None


def _table_empty(db, table: str) -> bool:
    return db.one(f"SELECT 1 FROM {table} LIMIT 1") is None  # noqa: S608 (table name is our own literal)


# ---- text.redflags ------------------------------------------------------------------------


def _fold(s: str) -> str:
    """Hindi is written with and without nukta (रोज़/रोज): drop it on both sides before matching."""
    return s.replace("\u093c?", "").replace("\u093c", "").replace("\u0901", "\u0902")


@lru_cache(maxsize=2048)
def _compiled(pat: str) -> tuple[re.Pattern, bool]:
    folded = _fold(pat)
    # a pattern that itself contains a negator ("loss nahi hoga", "कोई रिस्क नहीं") must not cancel itself
    own_negator = bool(_ASCII_NEGATORS.search(folded)) or any(t in folded for t in _HI_NEGATOR_TOKENS)
    return re.compile(folded, re.IGNORECASE), own_negator


# An awareness or warning sentence quotes scam phrases in order to warn ("Never trust schemes promising
# guaranteed returns", "गारंटीड रिटर्न ... से सावधान रहें"). Matches inside such a sentence are not claims.
_WARNING_CUES = re.compile(
    r"(?i)\b(never\s+(trust|share|pay|give|send|believe|invest)|do\s+not\s+(trust|share|pay|believe)|"
    r"don'?t\s+(trust|share|pay|believe)|beware|be\s+(careful|cautious|alert)|stay\s+away|watch\s+out|"
    r"avoid\s+(such|these|fake|fraud\w*|unregistered|scam\w*)|savdhan|bach\s*ke|bharosa\s+mat|"
    r"kabhi\s+mat|mat\s+karo|samajh\s+jao\s+scam|scam\s+hai)\b|सावधान|सतर्क|भरोसा\s*न|कभी\s*न|बचें|बचकर"
)
_SENTENCE = re.compile(r"[^.!?।\n]+[.!?।\n]*")


def _warning_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _SENTENCE.finditer(text) if _WARNING_CUES.search(m.group(0))]


# Short negators count only right next to the phrase: "not guaranteed", "no guarantee", "गारंटी नहीं".
_NEAR_NEGATOR_BEFORE = re.compile(r"(?i)\b(not|no|without|cannot|can'?t|nor)\W{1,3}$")
_NEAR_NEGATOR_AFTER = re.compile(r"(?i)^\W{0,3}(?:\S+\s+)?(नहीं|नही|nahi|nahin|not)(?![\w\u0900-\u097F])")
# A guarantee is genuine for small savings and deposits backed by the government ("डाकघर", "PPF", "FD").
_SAFE_GUARANTEE = re.compile(
    r"(?i)\b(post\s*office|ppf|nsc|fixed\s*deposit|fd|sovereign|government|govt|dicgc|deposit\s*insurance|"
    r"rbi\s*(floating\s*rate\s*)?bonds?)\b|पोस्ट\s*ऑफिस|डाकघर|सरकार|सरकारी|सुकन्या"
)


def _sentence_at(text: str, pos: int) -> str:
    for m in _SENTENCE.finditer(text):
        if m.start() <= pos < m.end():
            return m.group(0)
    return ""


def _match_lexicon(text: str, by_lang: dict[str, list[str]], code: str = "") -> list[str]:
    found = []
    text = _fold(text)
    warnings = _warning_spans(text)
    for patterns in by_lang.values():
        for pat in patterns or ():
            rx, own_negator = _compiled(pat)
            for m in rx.finditer(text):
                before = text[max(0, m.start() - _NEGATION_WINDOW) : m.start()]
                if _has_negator(before) or (not own_negator and _has_negator(m.group(0))):
                    continue  # "never share your OTP", "OTP kisi ko mat batao"
                if not own_negator and (
                    _NEAR_NEGATOR_BEFORE.search(text[max(0, m.start() - 12) : m.start()])
                    or _NEAR_NEGATOR_AFTER.search(text[m.end() : m.end() + 20])
                ):
                    continue  # "not guaranteed", "कोई गारंटी नहीं होती"
                if any(a <= m.start() < b for a, b in warnings):
                    continue  # the phrase is quoted in a warning, not offered
                if code == "GUARANTEED_RETURN" and _SAFE_GUARANTEE.search(_sentence_at(text, m.start())):
                    continue  # a government-backed deposit really is guaranteed
                found.append(m.group(0))
    return found


# Awareness and teaching messages quote scam phrases to warn about them. When a message reads like one
# and asks the reader to pay, call or click nothing of the sender's, its quoted phrases are not claims.
_AWARENESS = re.compile(
    r"(?i)\b(investor\s+awareness|awareness|psa|public\s+service|sebi\s+(cautions?|warns?|alerts?|advises?)|"
    r"report\s+(frauds?|scams?)|fraudsters?|scamsters?)\b|जागरूकता|सावधानी|धोखेबाज़?|ठगों"
)
_COUNTERPARTY_TYPES = frozenset({
    "upi.vpa", "upi.uri", "phone", "crypto.btc", "crypto.evm", "crypto.tron", "bank.account_no", "app.package",
    "apk.link", "tg.link", "email",
})


def _is_awareness_message(case: CaseState) -> bool:
    text = _message_text(case)
    if not _AWARENESS.search(_fold(text)) or not _warning_spans(_fold(text)):
        return False
    if any(e.type in _COUNTERPARTY_TYPES and e.cls == "C" for e in case.entities):
        return False
    official = {"sebi.gov.in", "rbi.org.in", "nseindia.com", "bseindia.com", "cybercrime.gov.in", "amfiindia.com", "scores.sebi.gov.in"}
    return all(ctx_dom in official for ctx_dom in (e.display.lower() for e in case.by_type("domain")))


_GUARANTEE_WORDS = ("guaranteed", "guarantee", "guranteed", "garanteed")


def _fuzzy_guarantee(text: str) -> str | None:
    """Typos such as 'garunteed', 'guarnteed', 'gauranteed' (lexicon regexes miss reordered letters)."""
    from rapidfuzz import fuzz

    for word in re.findall(r"(?i)\bg[a-z]{6,10}\b", text):
        w = word.lower()
        if any(fuzz.ratio(w, g) >= 80 for g in _GUARANTEE_WORDS):
            return word
    return None


_FIN_WORDS = re.compile(r"(?i)\b(invest\w*|returns?\w*|earn\w*|platform|scheme|income)\b|निवेश|कमाई")


def _celebrity_endorsement(text: str, brands: list[dict], window: int = 80) -> str | None:
    """A brands.yaml kind=celebrity alias within `window` chars of an investment word."""
    for b in brands:
        if b.get("kind") != "celebrity":
            continue
        for alias in b.get("aliases", ()):
            for m in re.finditer(re.escape(str(alias)), text, re.IGNORECASE):
                span = text[max(0, m.start() - window) : m.end() + window]
                if _FIN_WORDS.search(span):
                    return str(alias)
    return None


@register_checker
class TextRedflags(BaseChecker):
    id, family = "text.redflags", "text"
    description = "Scans the message for known scam phrases in English, Hindi and Hinglish."
    consumes = frozenset({"message.text"})
    produces = frozenset(
        {
            "FEE_TO_WITHDRAW", "REMOTE_ACCESS_REQUEST", "OTP_REQUEST", "DIGITAL_ARREST",
            "GUARANTEED_RETURN", "DABBA", "INSTITUTIONAL_ACCESS", "ACCOUNT_HANDLING",
            "URGENCY", "VIP_GROUP", "PUMP_LANGUAGE", "LIVE_CALLS", "CELEBRITY_ENDORSEMENT",
            "FAKE_REGULATOR_NOTICE", "INJECTION_TEXT", "KYC_PHISHING", "ADVANCE_FEE", "SIDELOAD_APK",
        }
    )
    privacy = "local"
    decisive = True  # FEE_TO_WITHDRAW / REMOTE_ACCESS_REQUEST / OTP_REQUEST / DIGITAL_ARREST are critical

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        text = ctx.raw(entity)
        if _is_awareness_message(ctx.case):
            return clear(facts={"awareness_message": True})  # it warns about these phrases; it does not use them
        lexicon = ctx.config.lexicons.get("redflags", {})
        codes: list[str] = []
        phrases: dict[str, list[str]] = {}
        for code, by_lang in lexicon.items():
            found = _match_lexicon(text, by_lang, code)
            if found:
                codes.append(code)
                phrases[code] = found
        if "GUARANTEED_RETURN" not in codes and (typo := _fuzzy_guarantee(_fold(text))):
            if _match_lexicon(text, {"x": [re.escape(typo)]}, "GUARANTEED_RETURN"):  # same negation/warning rules
                codes.append("GUARANTEED_RETURN")
                phrases["GUARANTEED_RETURN"] = [typo]
        celeb = _celebrity_endorsement(text, ctx.config.brands)
        if celeb:
            codes.append("CELEBRITY_ENDORSEMENT")
            phrases["CELEBRITY_ENDORSEMENT"] = [celeb]
        if not codes:
            return clear()
        return hit(*codes, basis="rule", facts={"phrases_raw": phrases})


# ---- text.return_math ----------------------------------------------------------------------

_DEFAULT_N_PER_YEAR = {"day": 250, "week": 52, "month": 12, "year": 1}
_DEFAULT_IMPOSSIBLE_THRESHOLD = 0.5
_MULTIPLE_CAP = 1e12  # ponytail: a sane display cap instead of float('inf') for absurd inputs


def _compound(rate: float, n: int) -> float:
    try:
        return math.exp(n * math.log1p(rate))
    except (OverflowError, ValueError):
        return _MULTIPLE_CAP


@register_checker
class TextReturnMath(BaseChecker):
    id, family = "text.return_math", "text"
    description = "Annualises a promised daily/weekly/monthly return; flags anything above 50% a year."
    consumes = frozenset({"money.return_rate"})
    produces = frozenset({"IMPOSSIBLE_RETURN"})
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        rate = entity.attrs.get("rate")
        period = entity.attrs.get("period")
        return_math = ctx.config.claim_rules.get("return_math", {})
        n = return_math.get("n_per_year", _DEFAULT_N_PER_YEAR).get(period)
        threshold = return_math.get("impossible_annual_return", _DEFAULT_IMPOSSIBLE_THRESHOLD)
        if rate is None or n is None:
            return unknown("bad_entity")
        if _is_awareness_message(ctx.case):
            return clear(facts={"awareness_message": True})
        context = _context_of(entity, ctx.case)
        near = _context_of(entity, ctx.case, window=20)
        if context is not None and ((near and _LOSS_WORDS.search(near)) or not _GAIN_WORDS.search(context)):
            return clear(facts={"not_a_promise": True})  # "Nifty falls 3% today" reports a move, promises nothing
        multiple = min(_compound(float(rate), n), _MULTIPLE_CAP)
        if multiple - 1 > threshold:
            return hit(
                "IMPOSSIBLE_RETURN",
                basis="rule",
                facts={
                    "yearly_multiple": round(multiple, 2),
                    "rate": rate,
                    "period": period,
                    "example_10000": round(10000 * multiple, 2),
                },
            )
        return clear()


# A rate is a promised return only next to gain words ("5% daily profit", "roz 3% munafa", "milega",
# "target") and not next to loss words ("falls 3% today", "3% girawat").
_GAIN_WORDS = re.compile(
    r"(?i)return|profit|munafa|मुनाफ|रिटर्न|earn|kamai|कमाई|कमाए|interest|ब्याज|income|guarant|गारंटी|pakka|पक्का|"
    r"double|डबल|target|टारगेट|milega|मिलेगा|मिलेंगे|पाएं|paao|get\s|growth|gain|payout|bonus|fixed"
)
# "loss" itself is left out: "bina kisi loss ke" / "no loss" is part of the promise, not a market report
_LOSS_WORDS = re.compile(r"(?i)\b(fall|falls|fell|drop|drops|dropped|down|crash\w*|declin\w*|slump\w*|plunge\w*)\b|गिर|गिरावट|girawat")


def _context_of(entity: Entity, case: CaseState, window: int = 60) -> str | None:
    """The message text around the entity's surface form; None when it cannot be located."""
    text = _message_text(case)
    surface = (entity.display or "").strip()
    pos = text.find(surface) if surface else -1
    if pos < 0:
        return None
    return text[max(0, pos - window) : pos + len(surface) + window]


# ---- claims.rules ---------------------------------------------------------------------------


def _code_for(entity: Entity, claim_rules: dict) -> str | None:
    spec = claim_rules.get("map", {}).get(entity.type)
    if spec is None:
        return None
    if isinstance(spec, str):
        return spec
    for rule in spec:
        when = rule.get("when", {})
        if all(entity.attrs.get(k) in (v if isinstance(v, list) else [v]) for k, v in when.items()):
            return rule.get("code")
    return None


_U_CLASS_PRESENCE_TYPES = frozenset({"aadhaar", "card.number", "otp"})


@register_checker
class ClaimsRules(BaseChecker):
    id, family = "claims.rules", "text"
    description = "Maps extracted claims (guaranteed return, fee-to-withdraw, remote access...) to risk codes."
    consumes = frozenset(
        {
            "claim.registered_as", "claim.impersonates", "claim.guaranteed_return", "claim.institutional_access",
            "claim.endorsement", "request.payment", "request.fee_to_withdraw", "request.install_app",
            "request.remote_access", "request.credentials", "request.kyc_docs", "request.join_group",
            "request.account_handling", "pressure.urgency", "tip.security_call", "offer.unregulated",
            "doc.official_notice", "threat.legal_action", "aadhaar", "card.number", "otp",
        }
    )
    produces = frozenset(
        {
            "GUARANTEED_RETURN", "FEE_TO_WITHDRAW", "REMOTE_ACCESS_REQUEST", "OTP_REQUEST", "DIGITAL_ARREST",
            "INSTITUTIONAL_ACCESS", "ACCOUNT_HANDLING", "URGENCY", "VIP_GROUP", "PUMP_LANGUAGE", "DABBA",
            "CRYPTO_PAYMENT_REQUEST", "CELEBRITY_ENDORSEMENT", "FAKE_REGULATOR_NOTICE", "REG_CLAIM_NO_NUMBER",
            "SENSITIVE_DATA_SHARED",
        }
    )
    privacy = "local"
    decisive = True  # DIGITAL_ARREST / FEE_TO_WITHDRAW / OTP_REQUEST / REMOTE_ACCESS_REQUEST are critical

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        basis = "rule" if entity.origin == "regex" else "llm_claim"
        if entity.type in _U_CLASS_PRESENCE_TYPES:
            return hit("SENSITIVE_DATA_SHARED", basis=basis)
        if entity.type == "claim.registered_as":
            has_number = any(
                (ref := ctx.case.entity(rid)) is not None and ref.type == "sebi.reg_no" for rid in entity.refs
            )
            return clear() if has_number else hit("REG_CLAIM_NO_NUMBER", basis=basis)
        if entity.type == "doc.official_notice":
            if ctx.case.by_type("request.payment"):
                return hit("FAKE_REGULATOR_NOTICE", basis=basis, facts={"issuer": entity.attrs.get("issuer", "")})
            return clear()
        code = _code_for(entity, ctx.config.claim_rules)
        return hit(code, basis=basis) if code else clear()


# ---- doc.notice -----------------------------------------------------------------------------


@register_checker
class DocNotice(BaseChecker):
    id, family = "doc.notice", "text"
    description = "An 'official SEBI/RBI/exchange notice' whose sender email isn't from the real domain."
    consumes = frozenset({"doc.official_notice", "email"})
    produces = frozenset({"FAKE_REGULATOR_NOTICE"})
    needs = ("db",)
    privacy = "local"

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:
        case = ctx.case
        impersonated = [c for c in case.by_type("claim.impersonates") if c.attrs.get("kind") in ("regulator", "exchange")]
        if not impersonated:
            return clear()
        if ctx.db is None or _table_empty(ctx.db, "official_domain"):
            return unknown("source_missing")
        emails = case.by_type("email") if entity.type == "doc.official_notice" else [entity]
        bad_domain = None
        for e in emails:
            d = registrable_domain(ctx.raw(e))
            if not _is_official(ctx.db, d):
                bad_domain = d
                break
        if bad_domain is None:
            return clear()
        brand = impersonated[0].attrs.get("org") or impersonated[0].attrs.get("brand_id") or ""
        return hit("FAKE_REGULATOR_NOTICE", basis="rule", facts={"brand": brand, "domain_raw": bad_domain})
