"""RulePlanner: entity type -> checkers, with no LLM (LLD §4.2; CONTRACTS cuts the LLM planner).

Called once per wave. Every entity is planned at most once in its lifetime: the first `plan()`
call that sees it (its `planned` flag still False) enumerates every consumer checker for its type
and never looks at it again, even if later waves re-plan other, newer entities. Waves happen
because *new* entities (derived by a checker, or merged from the LLM extraction) show up unplanned
in a later call, not because an old entity is reconsidered.
"""

from __future__ import annotations

from satark.checkers.registry import CheckerRegistry
from satark.harness.budget import Budget
from satark.harness.state import CaseState, PlanStep


class RulePlanner:
    def __init__(self, registry: CheckerRegistry, config) -> None:
        self.registry = registry
        self.config = config

    def plan(self, case: CaseState, mode: str, budget: Budget) -> list[PlanStep]:
        allow_privacy = frozenset((self.config.modes.get(mode) or {}).get("allow_privacy", []))
        done_keys = case.ledger_keys()
        planned_pairs = {(s.checker_id, s.entity_ids[0]) for s in case.plan.steps if s.entity_ids}

        new_steps: list[PlanStep] = []
        checked_per_type: dict[str, int] = {}
        for entity in case.entities:
            cap = (self.config.entities.get(entity.type) or {}).get("max_per_case")
            if cap is not None and checked_per_type.get(entity.type, 0) >= cap:
                entity.planned = True  # masked like the rest, but only the first N of a type are checked
                continue
            checked_per_type[entity.type] = checked_per_type.get(entity.type, 0) + 1
            if entity.planned:
                continue
            for checker in self.registry.consumers_of(entity.type, mode, allow_privacy):
                dedupe_key = (checker.id, entity.norm_hash or entity.id)
                if dedupe_key in done_keys or (checker.id, entity.id) in planned_pairs:
                    continue
                if not checker.should_run(entity, case):
                    continue
                new_steps.append(
                    PlanStep(id=case.next_id("s"), checker_id=checker.id, entity_ids=[entity.id], family=checker.family)
                )
            entity.planned = True

        kept = new_steps[: max(0, budget.tool_calls_left)]
        case.plan.steps.extend(kept)
        case.plan.revision += 1
        return kept
