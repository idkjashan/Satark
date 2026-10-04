"""Shared fixtures for tests/api/* (CONTRACTS §8: fixtures from tests/conftest.py plus a fake
runtime here, since D's real satark.harness.runtime does not exist yet)."""

from __future__ import annotations

import httpx
import pytest

from satark.app import create_app
from tests.api.fakes import build_fake_runtime


@pytest.fixture()
def rt(settings, config):
    return build_fake_runtime(settings, config)


@pytest.fixture()
async def client(settings, rt):
    app = create_app(settings=settings, runtime=rt)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
