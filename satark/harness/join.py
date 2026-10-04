"""Joiner: decides finish / next wave / wait / ask-user after each wave (LLD §4.3).

CONTRACTS.md cuts the LLM planner, so the LLM-re-plan row of the LLD table is dropped and
`AMBIGUOUS_MATCH` always falls straight through to `ASK_USER`. Rows 7 ("last wave added nothing")
and 8 ("otherwise") of the LLD table both mean FINISH and nothing above them changes that
conclusion, so they collapse into one default return — `last_wave_added` is accepted for
interface stability but has no row that reads it today.
"""

from __future__ import annotations

from typing import Literal

from satark.checkers.registry import CheckerRegistry
from satark.harness.budget import Budget
from satark.harness.score import Scorer
from satark.harness.state import AskUser, CaseState, Option

Decision = Literal["FINISH", "NEXT_WAVE", "WAIT_EXTRACTION", "ASK_USER"]

_MAX_CANDIDATES = 3


class Joiner:
    def __init__(self, registry: CheckerRegistry, scorer: Scorer, config) -> None:
        self.registry = registry
        self.scorer = scorer
        self.config = config

    def decide(
        self,
        case: CaseState,
        budget: Budget,
        extraction_pending: bool,
        last_wave_added: int,
        wave_no: int,
        max_waves: int,
    ) -> Decision:
        if budget.expired() or budget.verdict_expired() or wave_no >= max_waves:
            return "FINISH"

        preview = self.scorer.score(case)
        if preview.level == "HIGH_RISK" and preview.confidence == "SURE" and len(preview.reasons) >= 3:
            return "FINISH"  # nothing left can raise it further; get the stop to the user fast

        if any(not e.planned for e in case.entities):
            return "NEXT_WAVE"

        if extraction_pending:
            return "WAIT_EXTRACTION"

        if self._decisive_timeout_retryable(case, budget):
            return "NEXT_WAVE"

        question = self._ask_ambiguous(case)
        if question is not None:
            case.question = question
            return "ASK_USER"

        return "FINISH"

    def _decisive_timeout_retryable(self, case: CaseState, budget: Budget) -> bool:
        for ev in case.ledger:
            if ev.status != "unknown" or ev.reason != "timeout":
                continue
            checker = self.registry.get(ev.checker_id)
            if checker is not None and checker.decisive and budget.run_left() > checker.timeout_s:
                return True
        return False

    def _ask_ambiguous(self, case: CaseState) -> AskUser | None:
        for ev in case.ledger:
            if "AMBIGUOUS_MATCH" not in ev.flags:
                continue
            candidates = (ev.facts.get("candidates") or [])[:_MAX_CANDIDATES]
            # id is the candidate's reg_no itself: chat's _bind_choice creates a sebi.reg_no entity from it directly.
            options = [
                Option(id=c.get("reg_no", str(i)), label=f"{c.get('name', '?')} ({c.get('reg_no', '?')})")
                for i, c in enumerate(candidates)
            ]
            return AskUser(question_id=case.next_id("q"), text=self.config.t(case.lang, "ask.which_candidate"), options=options)
        return None
