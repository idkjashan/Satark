"""Shared fakes for harness unit tests. No network, no real checkers, no real LLMs.

Other engineers' modules (extraction, real checkers, SafeHttpClient) may not exist yet; these
fakes let D's tests run against docs/CONTRACTS.md shapes alone.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from satark.checkers.base import BaseChecker, CheckResult
from satark.checkers.registry import CheckerRegistry
from satark.harness.state import CaseState, Entity, EntityDraft


class FakeChecker(BaseChecker):
    """A checker whose `check()` is a plain async function passed in by the test."""

    def __init__(
        self,
        id: str,
        *,
        family: str = "link",
        consumes: frozenset[str] = frozenset({"url"}),
        produces: frozenset[str] = frozenset(),
        needs: tuple[str, ...] = (),
        source: str | None = None,
        privacy: str = "local",
        cost: int = 1,
        timeout_s: float = 2.5,
        cache_ttl_s: int = 0,
        decisive: bool = False,
        modes: frozenset[str] = frozenset({"check", "chat"}),
        run: Callable[[Entity, Any], Awaitable[CheckResult]] | None = None,
        should_run_fn: Callable[[Entity, CaseState], bool] | None = None,
    ) -> None:
        self.id = id
        self.family = family
        self.consumes = consumes
        self.produces = produces
        self.needs = needs
        self.source = source
        self.privacy = privacy
        self.cost = cost
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self.decisive = decisive
        self.modes = modes
        self._run = run
        self._should_run_fn = should_run_fn

    def should_run(self, entity: Entity, case: CaseState) -> bool:
        return self._should_run_fn(entity, case) if self._should_run_fn else True

    async def check(self, entity: Entity, ctx: Any) -> CheckResult:
        if self._run is None:
            raise NotImplementedError(f"FakeChecker {self.id} has no run()")
        return await self._run(entity, ctx)


def make_registry(*checkers: BaseChecker) -> CheckerRegistry:
    """A CheckerRegistry with these checkers indexed, bypassing full config validation."""
    reg = CheckerRegistry()
    for c in checkers:
        reg.add(c)
    reg._build_index()  # noqa: SLF001 (the index builder is the thing under indirect test)
    return reg


def make_entity(
    type: str = "url",  # noqa: A002 (matches Entity.type)
    *,
    id: str = "e1",  # noqa: A002
    cls: str = "C",
    value: str = "example.test",
    norm_hash: str | None = None,
    display: str | None = None,
    planned: bool = False,
    attrs: dict | None = None,
    role: str = "unknown",
) -> Entity:
    return Entity(
        id=id,
        type=type,
        cls=cls,
        value=value,
        norm_hash=norm_hash or hashlib.sha256(value.encode()).hexdigest(),
        display=display if display is not None else ("" if cls == "U" else value),
        planned=planned,
        attrs=attrs or {},
        role=role,
    )


@dataclass
class FakeExtraction:
    """Stands in for `satark.harness.extract.Extraction` (A's module)."""

    related_to_money: bool = True
    is_question: bool = False
    drafts: list[EntityDraft] = dataclass_field(default_factory=list)


class FakePipeline:
    """Stands in for `satark.harness.extract.ExtractorPipeline` (A's module).

    `regex_drafts` / `llm_result` are consumed once (set them again before the next call that
    should see new ones), mirroring how a real pipeline only reports entities it has not seen.
    """

    def __init__(self, regex_drafts: list[EntityDraft] | None = None, llm_result: FakeExtraction | None = None) -> None:
        self.added_drafts: list[EntityDraft] = []
        self.regex_drafts = list(regex_drafts or [])
        self.llm_result = llm_result
        self.regex_calls: list[str] = []
        self.llm_calls = 0

    def regex(self, case: CaseState, text: str, claims: bool = True, as_message: bool = True) -> list[Entity]:
        self.regex_calls.append(text)
        new = self.add_drafts(case, [EntityDraft(type="message.text", value=text)]) if text else []
        new += self.add_drafts(case, self.regex_drafts)
        self.regex_drafts = []
        return new

    def qr(self, case: CaseState, payload: str) -> list[Entity]:
        return []

    async def ocr(self, image: bytes, mime: str) -> str | None:
        return None

    async def llm(self, case: CaseState, image: bytes | None = None, image_mime: str | None = None) -> Any:
        self.llm_calls += 1
        return self.llm_result

    def merge(self, case: CaseState, extraction: Any) -> list[Entity]:
        if extraction is None:
            return []
        return self.add_drafts(case, list(getattr(extraction, "drafts", [])))

    def add_drafts(self, case: CaseState, drafts: list[EntityDraft], origin: str = "derived") -> list[Entity]:
        new: list[Entity] = []
        for d in drafts:
            norm_hash = hashlib.sha256(d.value.encode()).hexdigest()
            if any(e.type == d.type and e.norm_hash == norm_hash for e in case.entities):
                continue
            self.added_drafts.append(d)
            ent = Entity(
                id=case.next_id("e"),
                type=d.type,
                cls="C",
                value=d.value,
                norm_hash=norm_hash,
                display=d.value,
                role=d.role,
                origin=origin,
                attrs=d.attrs,
                refs=d.refs,
                quote=d.quote,
            )
            case.entities.append(ent)
            new.append(ent)
        return new


class FakeGuards:
    """Stands in for `satark.harness.guards` until A's module lands.

    Install in a test with e.g. `monkeypatch.setattr(respond_mod, "_guards", lambda: fake)` —
    each of D's modules resolves guards through its own private `_guards()` lazy-import helper.
    """

    def __init__(self, output_problems: list[str] | Callable[[str], list[str]] | None = None) -> None:
        self.output_problems = output_problems or []
        self.check_output_calls: list[str] = []

    def mask(self, text: str, case: CaseState) -> str:
        return text

    def unmask(self, text: str, case: CaseState, lang: str = "en") -> str:
        return text

    def brief(self, case: CaseState, role: str, config: Any) -> str:
        return "{}"

    def pii_leaks(self, prompt: str, case: CaseState) -> list[str]:
        return []

    def check_output(self, text: str, case: CaseState, config: Any, lang: str, expected_codes=None) -> list[str]:
        self.check_output_calls.append(text)
        return self.output_problems(text) if callable(self.output_problems) else list(self.output_problems)

    def is_advice_seeking(self, text: str) -> bool:
        return False

    def chip_ok(self, chip: str) -> bool:
        return bool(chip.strip())

    def scope(self, text: str, mode: str, in_case: bool = False) -> str:
        return "ok"
