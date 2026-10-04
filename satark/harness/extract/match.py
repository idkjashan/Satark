"""Low-level regex matching over `config/entities.yaml` pattern specs.

Shared by `pipeline.py` (the full extraction pass, every identifier type) and `guards.py`
(a U-class-only safety net rescan over fresh text). Keeping the compiler and matcher here
means both call sites agree on exactly how a pattern, its `context`/`window` and its
`normalise` function are applied.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from satark.harness.extract.fns import NORMALISERS
from satark.harness.extract.normalise import fold_pattern


@dataclass(frozen=True)
class CompiledPattern:
    pattern: re.Pattern
    context: re.Pattern | None = None
    window: int = 0


@dataclass(frozen=True)
class Match:
    type: str
    start: int
    end: int
    text: str  # original matched text (pre-normalise), used as `display`
    value: str  # after the type's `normalise` function
    attrs: dict[str, Any]  # extra attrs a normaliser returned alongside the value (e.g. return_rate)


def compile_patterns(entities_cfg: dict[str, dict[str, Any]]) -> dict[str, list[CompiledPattern]]:
    """One compile pass over every type's `patterns:` list. Cache the result per Config.

    `fold_pattern` is applied to every pattern and context string (harmless no-op on patterns
    with no Devanagari nukta/chandrabindu in them) so a literal Devanagari pattern still
    matches text that normalise_text() has already folded."""
    out: dict[str, list[CompiledPattern]] = {}
    for type_, spec in entities_cfg.items():
        compiled = []
        for p in spec.get("patterns") or []:
            if isinstance(p, str):
                compiled.append(CompiledPattern(pattern=re.compile(fold_pattern(p))))
            else:
                compiled.append(
                    CompiledPattern(
                        pattern=re.compile(fold_pattern(p["re"])),
                        context=re.compile(fold_pattern(p["context"])),
                        window=int(p.get("window", 40)),
                    )
                )
        if compiled:
            out[type_] = compiled
    return out


def _context_ok(pat: CompiledPattern, text: str, start: int, end: int) -> bool:
    if pat.context is None:
        return True
    before = text[max(0, start - pat.window) : start]
    after = text[end : end + pat.window]
    return bool(pat.context.search(before) or pat.context.search(after))


def apply_normalise(spec: dict[str, Any], raw: str) -> tuple[str, dict[str, Any]]:
    name = spec.get("normalise")
    fn = NORMALISERS.get(name) if name else None
    if fn is None:
        return raw.strip(), {}
    result = fn(raw)
    return result if isinstance(result, tuple) else (result, {})


def resolve_role(spec: dict[str, Any], text: str, start: int) -> str:
    """Role from `role_hints`: a regex tested against the ~80 chars just before the match."""
    for role, pat in (spec.get("role_hints") or {}).items():
        if re.search(fold_pattern(pat), text[max(0, start - 80) : start]):
            return role
    return "unknown"


def effective_class(spec: dict[str, Any], role: str) -> str:
    """R resolves to U when role is "user", else C; other classes are fixed in the YAML."""
    cls = spec["class"]
    return ("U" if role == "user" else "C") if cls == "R" else cls


# ---------------------------------------------------------------------------- text splicing

Span = tuple[int, int, str]


def outermost_spans(spans: list[Span]) -> list[Span]:
    """Drop a span fully contained in an already-kept one (e.g. a tg.link span inside its url
    span): text can only be replaced once per position, so the larger/outer match wins."""
    kept: list[Span] = []
    for s in sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]))):
        if kept and s[0] >= kept[-1][0] and s[1] <= kept[-1][1]:
            continue
        kept.append(s)
    return kept


def splice_spans(text: str, spans: list[Span]) -> str:
    """Replace each non-overlapping (start, end) span with its string, right to left."""
    for start, end, repl in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + repl + text[end:]
    return text


_TRAILING_PUNCT = ".,!?)।"  # danda (।) included: Hindi sentence-final punctuation


def find_matches(
    text: str,
    entities_cfg: dict[str, dict[str, Any]],
    compiled: dict[str, list[CompiledPattern]],
    types: Iterable[str] | None = None,
) -> list[Match]:
    """Every pattern match across `types` (default: every type `compiled` has patterns for)."""
    out: list[Match] = []
    wanted = compiled if types is None else {t: compiled[t] for t in types if t in compiled}
    for type_, pats in wanted.items():
        spec = entities_cfg[type_]
        for pat in pats:
            for m in pat.pattern.finditer(text):
                start, end = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                if type_ == "url":  # a url's greedy char class has no notion of sentence end
                    while end > start and text[end - 1] in _TRAILING_PUNCT:
                        end -= 1
                if start == end or not _context_ok(pat, text, start, end):
                    continue
                raw = text[start:end]
                value, attrs = apply_normalise(spec, raw)
                out.append(Match(type=type_, start=start, end=end, text=raw, value=value, attrs=attrs))
    return out
