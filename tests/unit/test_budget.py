"""Budget: time and tool-call accounting (LLD §3.6)."""

from __future__ import annotations

import time

from satark.harness.budget import Budget


def test_take_spends_and_refuses_when_short():
    b = Budget(verdict_deadline_s=9, run_deadline_s=12, tool_calls=3)
    assert b.take(2) is True
    assert b.tool_calls_left == 1
    assert b.take(2) is False  # unchanged: not enough left
    assert b.tool_calls_left == 1
    assert b.take(1) is True
    assert b.tool_calls_left == 0


def test_verdict_and_run_left_count_down():
    b = Budget(verdict_deadline_s=0.05, run_deadline_s=0.1, tool_calls=1)
    assert b.verdict_left() <= 0.05
    assert b.run_left() <= 0.1
    assert not b.verdict_expired()
    assert not b.expired()
    time.sleep(0.06)
    assert b.verdict_expired()
    assert b.verdict_left() == 0.0
    assert not b.expired()  # run deadline is longer, still alive
    time.sleep(0.05)
    assert b.expired()
    assert b.run_left() == 0.0


def test_left_never_negative():
    b = Budget(verdict_deadline_s=0, run_deadline_s=0, tool_calls=0)
    assert b.verdict_left() == 0.0
    assert b.run_left() == 0.0
    assert b.take(1) is False
