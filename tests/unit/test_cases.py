"""CaseStore: TTL, per-case locks, oldest-first eviction (LLD §3.7, §14.4)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from satark.harness import cases as cases_mod
from satark.harness.cases import CaseStore
from satark.harness.state import utcnow


def test_new_case_is_retrievable_with_its_lang_and_simple():
    store = CaseStore()
    case = store.new(lang="hi", simple=True)
    assert case.case_id
    assert store.get(case.case_id) is case
    assert case.lang == "hi"
    assert case.simple is True


def test_new_cases_get_distinct_ids():
    store = CaseStore()
    assert store.new().case_id != store.new().case_id


def test_get_missing_is_none():
    store = CaseStore()
    assert store.get("no-such-case") is None


def test_get_expired_is_none_and_forgotten():
    store = CaseStore()
    case = store.new()
    case.expires_at = utcnow() - timedelta(seconds=1)
    store.put(case)
    assert store.get(case.case_id) is None
    assert store.get(case.case_id) is None  # still gone on a second look


def test_put_updates_the_stored_case():
    store = CaseStore()
    case = store.new()
    case.lang = "hi"
    store.put(case)
    assert store.get(case.case_id).lang == "hi"


def test_lock_is_stable_per_case_and_distinct_across_cases():
    store = CaseStore()
    lock_a1, lock_a2, lock_b = store.lock("a"), store.lock("a"), store.lock("b")
    assert lock_a1 is lock_a2
    assert lock_a1 is not lock_b
    assert isinstance(lock_a1, asyncio.Lock)


def test_max_cases_drops_oldest_first(monkeypatch):
    monkeypatch.setattr(cases_mod, "MAX_CASES", 3)
    store = CaseStore()
    ids = [store.new().case_id for _ in range(4)]
    assert store.get(ids[0]) is None
    for cid in ids[1:]:
        assert store.get(cid) is not None
