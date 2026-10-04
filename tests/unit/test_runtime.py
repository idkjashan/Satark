"""Runtime: builds every shared object once, fails closed on bad config (CONTRACTS §5)."""

from __future__ import annotations

from dataclasses import replace

import pytest

import satark.harness.runtime as runtime_mod
from satark.checkers.registry import ConfigError
from satark.harness.runtime import build_runtime, close_runtime

pytest.importorskip("satark.harness.extract")
pytest.importorskip("satark.infra.http")


async def test_build_runtime_is_ready_with_the_fixture_db(settings):
    rt = await build_runtime(settings)
    try:
        assert rt.ready is True
        assert rt.not_ready_reason is None
        assert rt.db is not None
        assert rt.bus is not None
        assert rt.cases is not None
        assert rt.orchestrator is not None
        assert rt.orchestrator.active_runs() == 0
    finally:
        await close_runtime(rt)


async def test_build_runtime_not_ready_when_db_missing(settings, tmp_path):
    broken = replace(settings, db_path=tmp_path / "no-such-registry.db")
    rt = await build_runtime(broken)
    try:
        assert rt.ready is False
        assert rt.not_ready_reason == "registry database missing"
        assert rt.db is None
    finally:
        await close_runtime(rt)  # must not raise just because there is no db


async def test_config_error_propagates_fail_closed(settings, monkeypatch):
    def bad_load(root, validate=True):
        raise ConfigError("broken config")

    monkeypatch.setattr(runtime_mod, "load_config", bad_load)
    with pytest.raises(ConfigError):
        await build_runtime(settings)


async def test_close_runtime_closes_http_and_db_without_raising(settings):
    rt = await build_runtime(settings)
    await close_runtime(rt)  # no assertion beyond "doesn't raise" - db/http are C's/B's objects
