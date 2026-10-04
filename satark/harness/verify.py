"""Verifier: grounds the check agent's assessment before anything it says can count.

The model may find risks no rule names, which is how the harness generalises to new scam wording, but a
risk factor is kept only when it is anchored in facts:

- a judgement code (one the text checkers can raise: fees to withdraw, OTP requests, guaranteed returns...)
  or AI_RISK_PATTERN may be proved by quoting words that really appear in the message;
- a fact code (registry, domain age, .bank.in, phone series...) only by citing evidence ids from the checks
  whose results carry that same code: the model can repeat a checker's fact, never invent one;
- quoted factors never count when every UPI ID, number, app or site in the message checked out official
  (facts beat a reading of the wording), nor when the quote sits in a warning sentence ("never share your OTP"),
  the same reading the phrase rules apply;
- quoted factors count only when the model calls the input a message_to_check, in both the plan call and
  the assess call (two separate judgements must agree; the caller passes the agreed kind): a routine
  notice or a warning cannot carry risks found in its wording. A warning that names a counterparty (UPI ID,
  phone, wallet, account, app, Telegram link) is the exception: scams dress up as warnings.

Kept factors become one Evidence entry (checker "ai.assessment", family "ai", basis llm_claim). The
YAML scorer then sets the level from all evidence exactly as before: the model adds grounded evidence,
it never sets or lowers the level itself (CRITIC-style: verify model output against tools and facts).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from satark.checkers.text import _warning_spans
from satark.harness.state import CaseState, Evidence, SignalHit, SourceRef

AI_CODE = "AI_RISK_PATTERN"
HARMLESS_KINDS = frozenset({"routine_notice", "awareness_or_lesson"})
_RULE_TEXT_CHECKERS = frozenset({"text.redflags", "text.return_math", "upi.collect", "names.scan"})
_NOT_CLAIMABLE = frozenset({"INJECTION_TEXT", "SENSITIVE_DATA_SHARED"})  # facts about the input, not scam signs
_COUNTERPARTY_TYPES = frozenset({
    "upi.vpa", "upi.uri", "phone", "crypto.btc", "crypto.evm", "crypto.tron", "bank.account_no", "app.package",
    "apk.link", "tg.link",
})


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").replace("़", "").casefold()
    s = re.sub(r"</?untrusted_message>", " ", s)  # small models copy the wrapper tags into quotes
    s = re.sub(r"[\"'“”‘’`]", "", s)
    return " ".join(s.split()).strip(" .,;:!?।-")


def claimable_codes(registry, config) -> list[str]:
    """Judgement codes the model may prove with a quote: what the text-family checkers can raise."""
    codes = {c for ch in registry.all() if ch.family == "text" for c in ch.produces}
    return sorted(c for c in codes - _NOT_CLAIMABLE if config.signal(c).get("polarity") == "risk")


_NOTHING = re.compile(r"(?i)^\W*(nothing|none|no action|n/?a|-)?\W*$")


def asks_nothing(asks: str | None) -> bool:
    """The model itself said the sender asks the reader to do nothing (an informing, warning or teaching text)."""
    return asks is not None and bool(_NOTHING.match(asks.strip()))


def ground(factors: list[Any], case: CaseState, config, claimable=None, message_kind: str | None = None,
           observation_ids: set[str] | frozenset[str] = frozenset(), asks: str | None = None):
    """Split factors into (kept, problems). A factor has .code, .title, .quote, .evidence_ids.
    `observation_ids`: the agent loop's lookups (obs1...), which can prove a judgement code like a quote can."""
    message = _norm(case.masked_text)
    ledger = {ev.id: ev for ev in case.ledger}
    claimable = set(claimable or ()) | {AI_CODE}
    quotes_ok = (message_kind in (None, "message_to_check") or (
        message_kind == "awareness_or_lesson" and _names_counterparty(case, config))) and not (
        asks_nothing(asks) and not _names_counterparty(case, config))  # its own words: the text asks nothing
    official_only = _only_official_contacts(case, config)
    warnings = [_norm(case.masked_text[a:b]) for a, b in _warning_spans(case.masked_text)]
    kept, problems = [], []
    for f in factors:
        code = (f.code or "").strip().upper()
        spec = config.signals.get(code, {})
        if code != AI_CODE and spec.get("polarity") != "risk":
            problems.append(f"'{f.code}' is not a risk code in the catalogue; use a listed code or {AI_CODE}")
            continue
        quote = _norm(f.quote)
        quoted = (len(quote) >= 4 and quote in message) or any(i in observation_ids for i in f.evidence_ids)
        cited = [ledger[i] for i in f.evidence_ids if i in ledger]
        by_evidence = bool(cited) and any(code in {s.code for s in ev.signals} for ev in cited)
        if by_evidence:
            pass
        elif f.quote and not quoted:
            problems.append(f"the quote for {code} does not appear in the message: copy the exact words")
            continue
        # from here on "quoted" means proved by the message's words or by a lookup (obs id): a model reading
        elif not quoted:
            problems.append(f"{code} is not grounded: quote the message's exact words or cite evidence ids that show it")
            continue
        elif code not in claimable:
            problems.append(f"{code} is a fact only a check can show; cite its evidence id or use a judgement code")
            continue
        elif not quotes_ok:
            problems.append(f"{code}: only a message that asks the reader to act can have quoted risk factors "
                            f"(this is {message_kind}, asking {asks!r})")
            continue
        elif quote and any(quote in w for w in warnings):  # the rule pass's reading: "never share your OTP" warns
            problems.append(f"{code}: the quoted words are a warning sentence ('never share...'), not a request")
            continue
        elif official_only:  # facts beat a reading of the wording: every contact in it checked out official
            problems.append(f"{code}: every UPI ID, number, app or site in this message is official; a quoted risk "
                            "needs a rule or a check to agree")
            continue
        f.code = code
        kept.append(f)
    return kept, problems


# Checks that show a contact is the real institution's own (not merely "old" or "registered somewhere").
_OFFICIAL = frozenset({"UPI_VALID_HANDLE", "DOMAIN_OFFICIAL", "OFFICIAL_HELPLINE", "APP_IN_BROKER_REGISTRY",
                       "APP_SEBI_VERIFIED", "HANDLE_OFFICIAL"})


def _official_ids(case: CaseState, config) -> set[str]:
    return {eid for ev in case.ledger if ev.status in ("hit", "clear") for sig in ev.signals if sig.code in _OFFICIAL
            for eid in (sig.entity_ids or ev.entity_ids)}  # assurance signals arrive on "clear" results


def _names_counterparty(case: CaseState, config) -> bool:
    """A UPI ID, phone, wallet, account, app or Telegram link the reader could pay or contact, other than one a
    check showed is official (the 1930 helpline in an awareness post is not a counterparty)."""
    official = _official_ids(case, config)
    return any(e.type in _COUNTERPARTY_TYPES and e.cls == "C" and e.id not in official for e in case.entities)


def _only_official_contacts(case: CaseState, config) -> bool:
    """The message names something to pay, call, install or open, and checks showed every one of them is official
    (a broker's @valid UPI ID, an app in NSE's list, the bank's own domain, an official helpline)."""
    actionable = [e for e in case.entities if e.cls == "C" and e.type in _COUNTERPARTY_TYPES | {"domain"}]
    official = _official_ids(case, config)
    return bool(actionable) and all(e.id in official for e in actionable)


def to_evidence(case: CaseState, kept: list[Any], assessment: Any) -> Evidence:
    """One evidence entry for the verified assessment (family "ai")."""
    msg = case.by_type("message.text")
    entity_ids = [msg[0].id] if msg else []
    signals, titles, quotes = [], {}, {}
    for f in kept:
        if f.code in titles:
            continue  # a code counts once per case anyway
        signals.append(SignalHit(code=f.code, basis="llm_claim", entity_ids=entity_ids))
        titles[f.code] = f.title
        quotes[f.code] = f.quote
    return Evidence(
        id=case.next_id("ev"),
        step_id="ai",
        checker_id="ai.assessment",
        family="ai",
        entity_ids=entity_ids,
        status="hit" if signals else "clear",
        signals=signals,
        facts={
            "titles": titles,  # the AI's own reason sentences, shown for AI_RISK_PATTERN
            "quotes_raw": quotes,
            "scam_type": getattr(assessment, "scam_type", None),
            "message_kind": getattr(assessment, "message_kind", None),
        },
        source=SourceRef(id="ai"),
    )


def apply_message_kind(case: CaseState, assessment: Any, config) -> int:
    """The model judged the message a warning or a lesson: phrase-rule hits quote scams, they don't make
    one. Set those rule-only text evidence entries aside (status skipped). Facts from registries, lists and
    links still count, a message that asks the reader to pay or contact someone is never set aside, and
    neither is a critical phrase (OTP, remote access, fee to withdraw): one model judgement cannot undo it."""
    if getattr(assessment, "message_kind", None) != "awareness_or_lesson" or _names_counterparty(case, config):
        return 0
    n = 0
    for ev in case.ledger:
        critical = any(config.signal(sig.code).get("weight") == "critical" for sig in ev.signals)
        if ev.checker_id in _RULE_TEXT_CHECKERS and ev.status == "hit" and not critical:
            ev.status = "skipped"
            ev.reason = "ai_context:awareness_or_lesson"
            n += 1
    return n


def about_scam_types(case: CaseState, config) -> list[str]:
    """Scam types named by the phrase-rule hits that apply_message_kind set aside, most frequent first."""
    seen: Counter[str] = Counter()
    for ev in case.ledger:
        if ev.reason == "ai_context:awareness_or_lesson":
            for sig in ev.signals:
                seen.update(config.signal(sig.code).get("scam_types") or [])
    return [t for t, _ in seen.most_common()]
