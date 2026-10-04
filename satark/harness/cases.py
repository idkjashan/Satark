"""CaseStore: in-memory cases with a 30-minute TTL, plus one asyncio.Lock per case (LLD §3.7, §14.4).

ponytail: the content-hash cache (sha256 of normalised text + lang -> cached verdict/explanation,
6 h, LLD §14.4) is skipped. It only pays off once two people share byte-identical text, and reusing
it correctly requires the *new* case's regex entity ids to line up with the cached Verdict's
`entity_ids` (same extraction order) plus care that nothing in the cached payload is ever a raw
value. That's real coupling to A's not-yet-built extraction module for a sprint-day feature. Add it
in orchestrator.py (short-circuit after the regex pass on a content_hash hit) if the viral-forward
case shows up in the demo; until then every check runs for real.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict
from datetime import timedelta

from satark.harness.state import CaseState, utcnow

CASE_TTL = timedelta(minutes=30)
MAX_CASES = 5_000


class CaseStore:
    def __init__(self) -> None:
        self._cases: OrderedDict[str, CaseState] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    def new(self, lang: str = "en", simple: bool = False) -> CaseState:
        case = CaseState(case_id=secrets.token_urlsafe(16), lang=lang, simple=simple, expires_at=utcnow() + CASE_TTL)
        self.put(case)
        return case

    def get(self, case_id: str) -> CaseState | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        if case.expires_at <= utcnow():
            self._drop(case_id)
            return None
        return case

    def put(self, case: CaseState) -> None:
        self._cases[case.case_id] = case
        self._cases.move_to_end(case.case_id)
        while len(self._cases) > MAX_CASES:
            oldest_id, _ = self._cases.popitem(last=False)
            self._locks.pop(oldest_id, None)

    def lock(self, case_id: str) -> asyncio.Lock:
        lock = self._locks.get(case_id)
        if lock is None:
            lock = self._locks[case_id] = asyncio.Lock()
        return lock

    def _drop(self, case_id: str) -> None:
        self._cases.pop(case_id, None)
        self._locks.pop(case_id, None)
