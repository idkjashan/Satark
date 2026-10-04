"""Scorer: evidence ledger -> Verdict, pure and rule-driven from config/scoring.yaml (LLD §6.1).

"Deciding" signals (used for level matching and confidence) are a narrower set than "reasons"/
top: a level like NO_SIGNS matches on `completed_checks` alone, so it has zero deciding signals
even when a lone medium-weight risk code is present — that code is real but it didn't decide
anything, so it surfaces only in `worth_noting`. `reasons` is the sorted, capped subset of the
deciding codes actually shown on the card; any deciding code that doesn't make the cut (more
deciding codes than `max_reasons`) falls through to `worth_noting` too.
"""

from __future__ import annotations

from satark.harness.state import BASIS_STRENGTH, STRONG_BASIS, CaseState, FamilyStatus, Reason, Verdict

_SCAM_TYPE_WEIGHT = {"critical": 8, "high": 4, "medium": 2, "low": 1}
AI_CHECKER = "ai.assessment"


class Scorer:
    def __init__(self, config, registry=None) -> None:
        self.config = config
        self.registry = registry  # optional: only sharpens the "decisive checker" sort tie-break

    def score(self, case: CaseState) -> Verdict:
        config = self.config
        risk, assurances, all_codes_seen = self._collect(case)
        risk = self._drop_suppressed(risk, all_codes_seen)

        weight_counts: dict[str, int] = {}
        for info in risk.values():
            weight_counts[info["weight"]] = weight_counts.get(info["weight"], 0) + 1
        completed = sum(1 for ev in case.ledger if ev.status in ("hit", "clear"))

        level, deciding_weights = self._match_level(config.scoring.get("levels", {}), weight_counts, completed)
        deciding_codes = {c for c, info in risk.items() if info["weight"] in deciding_weights}
        # The model alone can say "be careful" but not "high risk": that needs a rule or a fact check to agree.
        cap = config.scoring.get("ai_only_max_level")
        if level == "HIGH_RISK" and cap and deciding_codes and all(risk[c]["ai_only"] for c in deciding_codes):
            level = cap
        confidence = self._confidence(deciding_codes, risk)

        weight_order = config.scoring.get("weight_order", ["critical", "high", "medium", "low"])
        ordered_codes = sorted(risk, key=lambda c: self._sort_key(risk[c], weight_order))
        max_reasons = int(config.scoring.get("max_reasons", 3))
        top_codes = [c for c in ordered_codes if c in deciding_codes][:max_reasons]
        reasons = [
            Reason(code=c, weight=risk[c]["weight"], basis=risk[c]["basis"], entity_ids=risk[c]["entity_ids"],
                   source=risk[c]["source"])
            for c in top_codes
        ]
        worth_noting = [c for c in ordered_codes if c not in top_codes]

        scam_type = self._scam_type(risk)
        return Verdict(
            revision=(case.verdict.revision + 1) if case.verdict else 1,
            level=level,
            confidence=confidence,
            reasons=reasons,
            worth_noting=worth_noting,
            assurances=sorted(assurances),
            actions=self._actions(level, top_codes),
            scam_type=scam_type,
            simulator=self._simulator(top_codes, ordered_codes),
            lesson=(config.scoring.get("lesson_by_scam_type") or {}).get(scam_type) if scam_type else None,
            checked=self._checked(case),
            scoring_version=str(config.scoring.get("version", "")),
        )

    # ---- collection -----------------------------------------------------------------------
    def _collect(self, case: CaseState) -> tuple[dict, set[str], set[str]]:
        risk: dict[str, dict] = {}
        assurances: set[str] = set()
        all_codes_seen: set[str] = set()
        for idx, ev in enumerate(case.ledger):
            checker = self.registry.get(ev.checker_id) if self.registry else None
            for sig in ev.signals:
                all_codes_seen.add(sig.code)
                spec = self.config.signal(sig.code)
                if spec.get("polarity") == "assurance":
                    assurances.add(sig.code)
                if spec.get("polarity") != "risk" or ev.status != "hit":
                    continue
                info = risk.get(sig.code)
                if info is None:
                    info = risk[sig.code] = {
                        "weight": spec.get("weight", "low"),
                        "basis": sig.basis,
                        "source": ev.source,
                        "entity_ids": [],
                        "decisive": False,
                        "stale": False,
                        "first_seen": idx,
                        "checkers": set(),
                    }
                info["checkers"].add(ev.checker_id)
                if ev.stale:
                    info["stale"] = True
                if checker is not None and checker.decisive:
                    info["decisive"] = True
                for eid in sig.entity_ids or ev.entity_ids:
                    if eid not in info["entity_ids"]:
                        info["entity_ids"].append(eid)
        picked = {e.id for e in case.entities if e.origin == "llm"}
        for info in risk.values():
            # only the AI review found it, or a check found it about something only the model pointed at (a name or
            # app it added): a wrong pick must not turn into a fact that decides High risk on its own
            info["ai_only"] = info["checkers"] == {AI_CHECKER} or (
                bool(info["entity_ids"]) and set(info["entity_ids"]) <= picked)
        return risk, assurances, all_codes_seen

    def _drop_suppressed(self, risk: dict, all_codes_seen: set[str]) -> dict:
        return {
            code: info
            for code, info in risk.items()
            if not any(s in all_codes_seen for s in self.config.signal(code).get("suppressed_by") or [])
        }

    # ---- level matching ---------------------------------------------------------------------
    def _match_level(self, levels_cfg: dict, weight_counts: dict, completed: int) -> tuple[str, set[str]]:
        for level, cond in levels_cfg.items():
            weights = self._matched_weights(cond, weight_counts, completed)
            if weights is not None:
                return level, weights
        return "UNKNOWN", set()

    def _matched_weights(self, cond: dict, weight_counts: dict, completed: int) -> set[str] | None:
        if cond.get("default"):
            return set()
        if "any" in cond:
            met = [(c, self._sub_met(c, weight_counts, completed)) for c in cond["any"]]
            return {c["weight"] for c, ok in met if ok and "weight" in c} if any(ok for _, ok in met) else None
        if "all" in cond:
            met = [(c, self._sub_met(c, weight_counts, completed)) for c in cond["all"]]
            return {c["weight"] for c, _ in met if "weight" in c} if all(ok for _, ok in met) else None
        return None

    def _sub_met(self, cond: dict, weight_counts: dict, completed: int) -> bool:
        if "weight" in cond:
            return weight_counts.get(cond["weight"], 0) >= cond.get("min", 1)
        if "completed_checks" in cond:
            return completed >= cond["completed_checks"]
        return False

    # ---- confidence -------------------------------------------------------------------------
    def _confidence(self, deciding_codes: set[str], risk: dict) -> str:
        if not deciding_codes:
            return "NOT_SURE"
        bases = [risk[c]["basis"] for c in deciding_codes]
        if any(b in STRONG_BASIS for b in bases):
            confidence = "SURE"
        elif sum(1 for c in deciding_codes if risk[c]["basis"] in ("rule", "llm_claim") and not risk[c].get("ai_only")) >= 2:
            confidence = "FAIRLY_SURE"
        elif any(len(risk[c].get("checkers", ())) >= 2 for c in deciding_codes):
            confidence = "FAIRLY_SURE"  # one risk found independently twice (e.g. a phrase rule and the AI review)
        else:
            confidence = "NOT_SURE"
        if confidence == "SURE" and any(risk[c]["stale"] for c in deciding_codes):
            confidence = "FAIRLY_SURE"
        return confidence

    # ---- ordering, actions, scam type, families --------------------------------------------
    def _sort_key(self, info: dict, weight_order: list[str]) -> tuple:
        w = weight_order.index(info["weight"]) if info["weight"] in weight_order else len(weight_order)
        b = BASIS_STRENGTH.index(info["basis"]) if info["basis"] in BASIS_STRENGTH else len(BASIS_STRENGTH)
        return (w, b, 0 if info["decisive"] else 1, info["first_seen"])

    def _actions(self, level: str, top_codes: list[str]) -> list[str]:
        defaults = list((self.config.scoring.get("default_actions") or {}).get(level, []))
        signal_actions = [a for c in top_codes for a in (self.config.signal(c).get("actions") or [])]
        ordered = defaults[:2] + signal_actions + defaults[2:]
        seen: set[str] = set()
        out = [a for a in ordered if not (a in seen or seen.add(a))]
        return out[: int(self.config.scoring.get("max_actions", 3))]

    def _scam_type(self, risk: dict) -> str | None:
        totals: dict[str, int] = {}
        for code, info in risk.items():
            for t in self.config.signal(code).get("scam_types") or []:
                totals[t] = totals.get(t, 0) + _SCAM_TYPE_WEIGHT.get(info["weight"], 0)
        return max(totals, key=lambda t: totals[t]) if totals else None

    def _simulator(self, top_codes: list[str], ordered_codes: list[str]) -> str | None:
        for code in top_codes + ordered_codes:
            sim = self.config.signal(code).get("simulator")
            if sim:
                return sim
        return None

    def _checked(self, case: CaseState) -> list[FamilyStatus]:
        families: list[str] = []
        for s in case.plan.steps:
            if s.family not in families:
                families.append(s.family)
        out = []
        for family in families:
            evs = [ev for ev in case.ledger if ev.family == family]
            if any(ev.status in ("hit", "clear") for ev in evs):
                status = "done"
            elif evs and all(ev.status == "skipped" for ev in evs):
                status = "skipped"
            else:
                status = "unknown"
            out.append(FamilyStatus(family=family, status=status))
        return out


def _sim_params(case: CaseState) -> dict | None:
    """Pre-fill simulator S2 with the promised rate from the message (text.return_math evidence)."""
    if case.verdict is None or case.verdict.simulator != "S2":
        return None
    for ev in case.ledger:
        if ev.checker_id == "text.return_math" and ev.status == "hit" and ev.facts.get("period") in ("day", "week", "month"):
            return {"rate": round(float(ev.facts["rate"]) * 100, 2), "period": ev.facts["period"]}
    return None


def verdict_event(case: CaseState, config) -> dict:
    """The `verdict` SSE payload (CONTRACTS §6.1), titles translated to the case's language."""
    v = case.verdict
    return {
        "revision": v.revision,
        "level": v.level,
        "confidence": v.confidence,
        "reasons": [
            {"code": r.code, "weight": r.weight, "title": _title(case, config, r.code),
             "source": {"id": r.source.id, "as_on": r.source.as_on}}
            for r in v.reasons
        ],
        "worth_noting": list(v.worth_noting),
        "assurances": list(v.assurances),
        "actions": list(v.actions),
        "scam_type": v.scam_type,
        "simulator": v.simulator,
        "sim_params": _sim_params(case),
        "lesson": v.lesson,
        "checked": [{"family": f.family, "status": f.status} for f in v.checked],
        "scoring_version": v.scoring_version,
        "ai_reviewed": v.ai_reviewed,
        "about_scam": v.about_scam,
    }


def _title(case: CaseState, config, code: str) -> str:
    """Catalogue title in the case's language. A risk only the AI review found shows the model's own sentence
    (guard-checked, next to a verified quote): it says what the model actually saw, even when the catalogue
    code it picked is only the nearest fit."""
    found_by_rules = any(ev.checker_id != AI_CHECKER and ev.status == "hit" and code in {s.code for s in ev.signals}
                         for ev in case.ledger)
    if not found_by_rules:
        for ev in case.ledger:
            if ev.checker_id == AI_CHECKER and (t := (ev.facts.get("titles") or {}).get(code)):
                return t
    return config.t(case.lang, f"signal.{code}")
