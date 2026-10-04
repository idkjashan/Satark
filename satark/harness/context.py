"""Context management for the agent loop: what goes into each model call, within a token budget.

Small local models have small windows (Ollama's default is 4,096 tokens), so every prompt is built from
prioritised sections and trimmed to fit, in this order: older observations shrink to one line, then clear
check results drop out of the brief, then the oldest observations and conversation turns go. The newest
observations and the task line are never dropped. Token counts are estimates (about 3.5 Latin characters
or 1.5 Devanagari characters per token), which is close enough to keep calls inside the window.
"""

from __future__ import annotations

from dataclasses import dataclass

from satark.harness.state import CaseState, Observation

_NOT_SHOWN = frozenset({"message.text"})


def tokens(text: str) -> int:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return int(ascii_chars / 3.5 + (len(text) - ascii_chars) / 1.5) + 1


def one_line(obs: Observation) -> str:
    first = obs.text.strip().splitlines()[0] if obs.text.strip() else ("failed" if not obs.ok else "no result")
    return f"[{obs.id}] {obs.tool}: {first[:140]}"


def full(obs: Observation, limit: int = 700) -> str:
    return f"[{obs.id}] {obs.tool}: {obs.text.strip()[:limit] or ('failed' if not obs.ok else 'no result')}"


def render_observations(observations: list[Observation], budget: int) -> str:
    """Newest first in full, older ones as one line, oldest dropped, all within `budget` tokens."""
    if not observations:
        return ""
    lines: list[str] = []
    used = 0
    latest_step = max(o.step for o in observations)
    for obs in reversed(observations):
        text = full(obs) if obs.step == latest_step else one_line(obs)
        cost = tokens(text)
        if used + cost > budget:
            text = one_line(obs)
            cost = tokens(text)
            if used + cost > budget:
                break
        lines.append(text)
        used += cost
    return "\n".join(reversed(lines))


def compact_brief(case: CaseState, config, mask, drop_clear: bool = False) -> str:
    """The case in a few lines: masked message, screenshot reading, identifiers with their check status,
    rule findings. `mask` is guards.mask (re-masks names found after the text was masked)."""
    parts = [f"<untrusted_message>{mask(case.masked_text, case)[:1500]}</untrusted_message>"]
    if case.image and (case.image.screen or case.image.description):
        cues = f"; seen: {', '.join(mask(c, case) for c in case.image.cues[:5])}" if case.image.cues else ""
        parts.append(f"Screenshot: {mask(case.image.screen, case)} - {mask(case.image.description, case)}{cues}")
    status: dict[str, list[str]] = {}
    for ev in case.ledger:
        if ev.checker_id == "ai.assessment":
            continue
        for eid in ev.entity_ids:
            codes = [s.code for s in ev.signals]
            if codes or not drop_clear:
                status.setdefault(eid, []).append(f"{ev.checker_id} {ev.status}{' ' + '/'.join(codes) if codes else ''}")
    ids = []
    for e in case.entities:
        if e.type in _NOT_SHOWN or e.type.startswith("claim.") or not e.placeholder:
            continue
        kind = f" ({e.attrs['kind']})" if e.attrs.get("kind") else ""
        checked = "; ".join(status.get(e.id, [])[:4]) or ("not checked" if not e.planned else "checked, nothing found")
        ids.append(f"{e.id} {e.placeholder} {e.type}{kind}: {checked}")
    if ids:
        parts.append("Identifiers:\n" + "\n".join(ids))
    v = case.verdict
    if v and (v.reasons or v.worth_noting):
        found = [f"{r.code}: {config.t('en', f'signal.{r.code}')}" for r in v.reasons]
        found += [f"{c} (worth noting)" for c in v.worth_noting[:4]]
        parts.append("Rule findings: " + "; ".join(found))
    elif v:
        parts.append("Rule findings: none")
    return "\n".join(parts)


@dataclass
class Section:
    text: str
    keep: bool = False  # never trimmed (the task line, the message)


def fit(sections: list[Section], budget: int) -> str:
    """Join sections; when over budget, cut the longest trimmable section first, line by line from its start
    (older content comes first in every section), until the prompt fits."""
    texts = [s.text for s in sections]
    while sum(tokens(t) for t in texts) > budget:
        trimmable = [i for i, s in enumerate(sections) if not s.keep and texts[i]]
        if not trimmable:
            break
        i = max(trimmable, key=lambda j: tokens(texts[j]))
        lines = texts[i].splitlines()
        texts[i] = "\n".join(lines[1:]) if len(lines) > 1 else texts[i][: len(texts[i]) // 2]
        if len(lines) <= 1 and tokens(texts[i]) < 8:
            texts[i] = ""
    return "\n\n".join(t for t in texts if t.strip())
