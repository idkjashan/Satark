"""The checker plugin contract (LLD §5.1).

A checker is a small class registered with @register_checker. It takes one entity
and returns a CheckResult. Checkers only read; they must be safe to call twice.

    @register_checker
    class UpiValidHandle(BaseChecker):
        id, family = "upi.valid_handle", "payment"
        description = "Is this UPI ID a SEBI @valid handle?"
        consumes = frozenset({"upi.vpa"})
        produces = frozenset({"UPI_VALID_HANDLE", "UPI_PERSONAL_WHILE_CLAIMING_SEBI"})
        decisive = True

        async def check(self, entity, ctx):
            ...
            return clear("UPI_VALID_HANDLE", basis="rule", facts={"suffix": "brk"})
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from satark.harness.state import (
    Basis,
    CaseState,
    CheckResult,
    Entity,
    EntityDraft,
    Privacy,
    SignalHit,
    SourceRef,
    utcnow,
)

if TYPE_CHECKING:  # avoid import cycles at runtime
    from satark.config import Config
    from satark.infra.db import RegistryDB

FAMILIES = ("registry", "payment", "link", "app", "phone", "text", "social", "ai")

_REGISTERED: list[type] = []


def register_checker(cls: type) -> type:
    """Class decorator: remember the checker class; CheckerRegistry.discover() instantiates it."""
    _REGISTERED.append(cls)
    return cls


def registered_classes() -> list[type]:
    return list(_REGISTERED)


class BaseChecker:
    """Defaults so a plugin only sets what differs. See LLD §5.1 for each attribute."""

    id: ClassVar[str] = ""
    family: ClassVar[str] = ""
    description: ClassVar[str] = ""
    consumes: ClassVar[frozenset[str]] = frozenset()
    produces: ClassVar[frozenset[str]] = frozenset()  # every signal AND flag code it may emit
    needs: ClassVar[tuple[str, ...]] = ()  # "db", "http", "secret:NAME"
    source: ClassVar[str | None] = None  # sources id whose breaker/rate limit/freshness applies
    privacy: ClassVar[Privacy] = "local"  # what leaves the server: nothing / a public id / a personal id
    cost: ClassVar[int] = 1  # 1 local, 2 free API, 3 rate-limited API
    timeout_s: ClassVar[float] = 2.5
    cache_ttl_s: ClassVar[int] = 0  # 0 = no cache, -1 = until the data version changes; only for results that
    # depend on the entity value alone (never on the case's claims), since the cache is shared across cases
    decisive: ClassVar[bool] = False  # its signals can set HIGH_RISK alone; planned first
    modes: ClassVar[frozenset[str]] = frozenset({"check", "chat"})

    def should_run(self, entity: Entity, case: CaseState) -> bool:  # cheap pre-filter
        return True

    async def check(self, entity: Entity, ctx: CheckContext) -> CheckResult:  # pragma: no cover
        raise NotImplementedError


@dataclass
class CheckContext:
    """Everything a checker may touch. Built by the executor per call."""

    case: CaseState  # treat as read-only
    config: Config
    db: RegistryDB | None = None
    http: Any = None  # satark.infra.http.SafeHttpClient
    secrets: Mapping[str, str] = field(default_factory=dict)
    now: datetime = field(default_factory=utcnow)

    def raw(self, entity: Entity) -> str:
        """The real (normalised) value of an entity. Only checkers call this."""
        return entity.value.get_secret_value()


class TransientError(Exception):
    """Raise from a checker for connection errors, HTTP 5xx or 429: the executor retries once."""


# ---- result helpers ---------------------------------------------------------------------


def _hits(codes: Iterable[str] | str, basis: Basis, entity_ids: list[str] | None) -> list[SignalHit]:
    if isinstance(codes, str):  # assure="REG_FOUND" is a common call shape
        codes = (codes,)
    return [SignalHit(code=c, basis=basis, entity_ids=list(entity_ids or [])) for c in codes]


def hit(
    *codes: str,
    basis: Basis = "rule",
    facts: dict[str, Any] | None = None,
    flags: Iterable[str] = (),
    derived: Iterable[EntityDraft] = (),
    source: SourceRef | None = None,
    entity_ids: list[str] | None = None,
    assure: Iterable[str] | str = (),
) -> CheckResult:
    """Checked, at least one risk signal. `assure` adds assurance codes found in the same check."""
    return CheckResult(
        status="hit",
        facts=facts or {},
        signals=_hits(codes, basis, entity_ids) + _hits(assure, basis, entity_ids),
        flags={flags} if isinstance(flags, str) else set(flags),
        derived=list(derived),
        source=source or SourceRef(),
    )


def clear(
    *assure: str,
    basis: Basis = "rule",
    facts: dict[str, Any] | None = None,
    flags: Iterable[str] = (),
    derived: Iterable[EntityDraft] = (),
    source: SourceRef | None = None,
    entity_ids: list[str] | None = None,
) -> CheckResult:
    """Checked, no risk signal. `assure` codes are assurance/info signals ("what we checked")."""
    return CheckResult(
        status="clear",
        facts=facts or {},
        signals=_hits(assure, basis, entity_ids),
        flags=set(flags),
        derived=list(derived),
        source=source or SourceRef(),
    )


def unknown(reason: str, source: SourceRef | None = None, facts: dict[str, Any] | None = None) -> CheckResult:
    """Could not check (timeout, source missing, rate limited). Never a guess."""
    return CheckResult(status="unknown", reason=reason, source=source or SourceRef(), facts=facts or {})
