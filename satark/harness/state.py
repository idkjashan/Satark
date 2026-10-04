"""Domain models shared by every part of the harness (LLD §3.3).

Everything here is a Pydantic model so it serialises to JSON for events and tests.
Raw identifier values live only in `Entity.value` (a SecretStr): it is never
serialised in clear, never logged and never put into an LLM prompt. Checkers read
it through `CheckContext.raw(entity)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr

Status = Literal["hit", "clear", "unknown", "error", "skipped"]
Basis = Literal["registry", "official_list", "threat_feed", "rule", "llm_claim"]
EntityClass = Literal["U", "C", "P"]
Role = Literal["payee", "caller", "sender", "claimed_entity", "user", "unknown"]
Origin = Literal["regex", "llm", "qr", "derived"]
Level = Literal["HIGH_RISK", "SUSPICIOUS", "NO_SIGNS", "UNKNOWN"]
Confidence = Literal["SURE", "FAIRLY_SURE", "NOT_SURE"]
StepStatus = Literal["pending", "running", "done", "unknown", "skipped"]
Privacy = Literal["local", "public_only", "identifier"]

BASIS_STRENGTH: tuple[Basis, ...] = ("registry", "official_list", "threat_feed", "rule", "llm_claim")
STRONG_BASIS: frozenset[str] = frozenset({"registry", "official_list", "threat_feed"})


def utcnow() -> datetime:
    return datetime.now(UTC)


class Entity(BaseModel):
    """One typed item found in the input (a UPI ID, a URL, a claim...)."""

    id: str  # "e1", "e2"... unique within the case
    type: str  # entity type id from config/entities.yaml, e.g. "upi.vpa"
    cls: EntityClass  # U = user's own data, C = counterparty, P = public (R types are resolved to U or C)
    placeholder: str = ""  # "[UPI_1]"; empty for P-class and claim types
    norm_hash: str = ""  # sha256 hex of the normalised value (dedupe + cache keys)
    value: SecretStr = SecretStr("")  # normalised raw value; "" for U-class (discarded)
    display: str = ""  # what the user sees: original text for C/P, "" for U
    role: Role = "unknown"
    origin: Origin = "regex"
    attrs: dict[str, Any] = Field(default_factory=dict)  # safe, LLM-visible attributes (psp_handle, domain, category...)
    refs: list[str] = Field(default_factory=list)  # other entity ids (claims point at names and numbers)
    quote: str = ""  # masked surrounding text (claims), <=120 chars
    valid: bool = True  # False when a checksum failed (likely OCR misread)
    planned: bool = False  # set by the planner once its consumers are planned


class EntityDraft(BaseModel):
    """A new entity proposed by a checker (derived) or by the LLM extraction."""

    type: str
    value: str = ""
    role: Role = "unknown"
    attrs: dict[str, Any] = Field(default_factory=dict)
    refs: list[str] = Field(default_factory=list)
    quote: str = ""


class SignalHit(BaseModel):
    code: str  # from config/signals.yaml
    basis: Basis
    entity_ids: list[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    id: str | None = None  # config/sources.yaml id or live-service id, e.g. "sebi_registers", "rdap"
    as_on: str | None = None  # ISO date of the data


class CheckResult(BaseModel):
    """What a checker returns. Build it with the helpers in satark.checkers.base."""

    status: Status
    facts: dict[str, Any] = Field(default_factory=dict)
    signals: list[SignalHit] = Field(default_factory=list)  # risk, assurance and info codes
    flags: set[str] = Field(default_factory=set)  # e.g. {"AMBIGUOUS_MATCH"}; never scored
    derived: list[EntityDraft] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=SourceRef)
    reason: str | None = None  # for unknown/error/skipped: "timeout", "source_missing", "budget"...


class Evidence(BaseModel):
    id: str  # "ev1"...
    step_id: str
    checker_id: str
    family: str
    entity_ids: list[str]
    status: Status
    facts: dict[str, Any] = Field(default_factory=dict)
    signals: list[SignalHit] = Field(default_factory=list)
    flags: set[str] = Field(default_factory=set)
    derived_ids: list[str] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=SourceRef)
    reason: str | None = None
    stale: bool = False
    cached: bool = False
    latency_ms: int = 0


class PlanStep(BaseModel):
    id: str  # "s1"... unique within the case
    checker_id: str
    entity_ids: list[str]
    depends_on: list[str] = Field(default_factory=list)
    family: str
    why: str = ""
    status: StepStatus = "pending"


class Plan(BaseModel):
    revision: int = 0
    created_by: Literal["rules", "llm"] = "rules"
    steps: list[PlanStep] = Field(default_factory=list)


class Reason(BaseModel):
    """One deciding risk signal in a verdict."""

    code: str
    weight: str
    basis: Basis
    entity_ids: list[str] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=SourceRef)


class FamilyStatus(BaseModel):
    family: str
    status: Literal["done", "unknown", "skipped"]  # unknown = "could not check"


class Verdict(BaseModel):
    revision: int = 1
    level: Level
    confidence: Confidence
    reasons: list[Reason] = Field(default_factory=list)  # top <=3 risk signals
    worth_noting: list[str] = Field(default_factory=list)  # other risk codes that did not set the level
    assurances: list[str] = Field(default_factory=list)  # assurance codes found ("what we checked")
    actions: list[str] = Field(default_factory=list)  # action ids from content/portals.json, <=3
    scam_type: str | None = None  # T1..T17
    simulator: str | None = None  # S1/S2/S3 from the top signal, drives "See how this trap works"
    lesson: str | None = None  # content/lessons/<id>.json picked by scam type (scoring.yaml lesson_by_scam_type)
    checked: list[FamilyStatus] = Field(default_factory=list)
    scoring_version: str = ""
    about_scam: bool = False  # the text describes a known scam (awareness, news) and asks nothing of the reader
    ai_reviewed: bool = False  # True once the AI assessment (verified) has been folded in


class ReasonText(BaseModel):
    code: str
    text: str


class Explanation(BaseModel):
    summary: str
    reasons: list[ReasonText] = Field(default_factory=list)
    chips: list[str] = Field(default_factory=list)  # 2-3 follow-up questions
    fallback_used: bool = False
    lang: str = "en"


class ChatAnswer(BaseModel):
    text: str = Field(description="The answer for the user, plain text, at most 120 words, in the user's language")
    cites: list[str] = Field(default_factory=list, description="Evidence ids (ev1, ev2...) the answer relies on")
    actions: list[str] = Field(default_factory=list, description="Action ids from the allowed list, at most 3")
    chips: list[str] = Field(default_factory=list, description="2-3 short follow-up questions the user may tap")
    refused: Literal["off_topic", "advice"] | None = Field(
        default=None,
        description="Set when declining: off_topic = unrelated to money safety or financial learning; "
        "advice = a request for a stock tip, buy/sell call or personal investment recommendation",
    )
    fallback_used: bool = False


class Option(BaseModel):
    id: str
    label: str


class AskUser(BaseModel):
    question_id: str
    text: str
    options: list[Option] = Field(default_factory=list)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str  # masked


class Observation(BaseModel):
    """One tool result the agent loop saw (obs1, obs2...). Kept on the case: it is the loop's memory across
    steps and chat turns, and the judge may cite it as proof. `text` is masked; `label` is for display."""

    id: str
    tool: str
    label: str = ""
    ok: bool = True
    text: str = ""
    step: int = 0
    key: str = ""  # tool + arguments: the same lookup is never run twice for a case


class ImageReading(BaseModel):
    """What a local vision model saw in a screenshot (masked once the case's identifiers are known)."""

    screen: str = ""
    description: str = ""
    cues: list[str] = Field(default_factory=list)


class CaseState(BaseModel):
    """Everything known about one shared item, kept in memory for 30 minutes."""

    case_id: str
    lang: str = "en"
    simple: bool = False
    content_hash: str = ""
    masked_text: str = ""  # the input text with every U and C value replaced by its placeholder
    entities: list[Entity] = Field(default_factory=list)
    ledger: list[Evidence] = Field(default_factory=list)
    plan: Plan = Field(default_factory=Plan)
    verdict: Verdict | None = None
    explanation: Explanation | None = None
    turns: list[Turn] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    image: ImageReading | None = None
    question: AskUser | None = None
    expires_at: datetime = Field(default_factory=utcnow)
    counters: dict[str, int] = Field(default_factory=dict)  # next ids: {"e": 3, "s": 5, "ev": 7, "UPI": 2}

    # --- small helpers used everywhere -------------------------------------------------
    def next_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}{n}"

    def entity(self, entity_id: str) -> Entity | None:
        return next((e for e in self.entities if e.id == entity_id), None)

    def by_type(self, type_: str) -> list[Entity]:
        return [e for e in self.entities if e.type == type_]

    def claim(self, type_: str) -> Entity | None:
        """First entity of a claim type, e.g. case.claim("claim.registered_as")."""
        return next((e for e in self.entities if e.type == type_), None)

    def ledger_keys(self) -> set[tuple[str, str]]:
        """(checker_id, norm_hash) pairs already checked, for dedupe."""
        keys: set[tuple[str, str]] = set()
        for ev in self.ledger:
            for eid in ev.entity_ids:
                ent = self.entity(eid)
                if ent is not None:
                    keys.add((ev.checker_id, ent.norm_hash or ent.id))
        return keys


class Event(BaseModel):
    """One SSE event. `id` increases per run; `type` is the SSE event name."""

    id: int
    type: str
    data: dict[str, Any]
