"""Shared test fixtures. Tests never touch the network: see docs/CONTRACTS.md §8."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

from satark.config import ROOT, Config, Settings, load_config
from satark.harness.state import CaseState, utcnow
from satark.infra.db import RegistryDB
from tests.fixtures.fixture_db import build_fixture_db

# No test may reach a real model provider (LLD §26.1).
try:
    from pydantic_ai import models as _models

    _models.ALLOW_MODEL_REQUESTS = False
except Exception:  # pragma: no cover
    pass


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SATARK_NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="network test; set SATARK_NETWORK_TESTS=1")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def config() -> Config:
    """Config from the repo, without cross-validation (content may still be in progress)."""
    return load_config(ROOT, validate=False)


@pytest.fixture(scope="session")
def fixture_db_path(tmp_path_factory) -> Path:
    return build_fixture_db(tmp_path_factory.mktemp("db") / "registry.db")


@pytest.fixture()
def fixture_db(fixture_db_path) -> RegistryDB:
    db = RegistryDB(fixture_db_path)
    yield db
    db.close()


@pytest.fixture()
def settings(fixture_db_path, tmp_path) -> Settings:
    """Offline settings over the fixture DB."""
    return Settings.from_env(db_path=fixture_db_path, network=False, web_dist=tmp_path / "no-dist",
                             env={"SATARK_RATE_LIMIT_SCALE": "0"})


@pytest.fixture()
def make_case():
    def _make(lang: str = "en", simple: bool = False, case_id: str = "case-test") -> CaseState:
        return CaseState(case_id=case_id, lang=lang, simple=simple, expires_at=utcnow() + timedelta(minutes=30))

    return _make


@pytest.fixture(autouse=True)
def _fresh_checker_caches():
    """Module-level caches (e.g. fetched Play pages) must not leak between tests."""
    from satark.checkers import apps

    apps._PAGE_CACHE.clear()
    yield
