"""Both MCP servers, spawned for real over stdio (CONTRACTS §8: tests never touch the network).

websearch.py always runs its `fake` backend here. satark_server.py runs fully offline
(SATARK_OFFLINE=1, every SATARK_LLM* var stripped) over the real data/registry.db, exactly like
`scripts/eval_set.py` without a model configured: rules only, no network, no LLM call.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import CallToolResult

WEBSEARCH_ENV = {"SATARK_WEBSEARCH_BACKEND": "fake"}


def _satark_env() -> dict[str, str]:
    """Offline, rules-only: every SATARK_LLM* var stripped so no model role can turn on."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SATARK_LLM")}
    env["SATARK_OFFLINE"] = "1"
    return env


@asynccontextmanager
async def _session(module: str, extra_env: dict[str, str]) -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", module], env={**os.environ, **extra_env}
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def _data(result: CallToolResult) -> dict:
    """A tool here always returns a plain dict, which the SDK JSON-dumps into one text block
    (bare `-> dict` gets no output_schema, so there is no structured_content - see
    mcp.server.mcpserver.utilities.func_metadata._create_output_model)."""
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


# ---- websearch.py ---------------------------------------------------------------------------


async def test_websearch_lists_search_tool_with_schema():
    async with _session("satark.mcp_servers.websearch", WEBSEARCH_ENV) as session:
        tools = (await session.list_tools()).tools
        assert [t.name for t in tools] == ["search"]
        props = tools[0].input_schema["properties"]
        assert props.keys() >= {"query", "max_results"}
        assert props["query"]["type"] == "string"


async def test_websearch_fake_backend_returns_results():
    async with _session("satark.mcp_servers.websearch", WEBSEARCH_ENV) as session:
        result = await session.call_tool("search", {"query": "acme trading scam", "max_results": 5})
        data = _data(result)
        assert data["query"] == "acme trading scam"
        assert data["error"] is None
        titles = [r["title"] for r in data["results"]]
        assert len(titles) >= 2
        assert all("acme trading scam" in t for t in titles[:2])
        assert any("reported as a scam" in t for t in titles)


async def test_websearch_refuses_queries_with_personal_data():
    async with _session("satark.mcp_servers.websearch", WEBSEARCH_ENV) as session:
        for query in (
            "call me urgently on 9876543210 today",  # phone-like: 10+ digit run
            "pay to rajesh@okaxis for the premium plan",  # UPI id (no dot, so not an email)
            "my aadhaar number is 234512349012 verify now",  # 12-digit Aadhaar-like number
        ):
            result = await session.call_tool("search", {"query": query})
            data = _data(result)
            assert data["results"] == []
            assert data["error"]


# ---- satark_server.py -----------------------------------------------------------------------


async def test_satark_server_tools_and_checks():
    async with _session("satark.mcp_servers.satark_server", _satark_env()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert set(tools) == {"check_message", "search_sebi_register", "check_identifier"}
        assert "text" in tools["check_message"].input_schema["properties"]
        assert "name" in tools["search_sebi_register"].input_schema["properties"]
        assert {"kind", "value"} <= tools["check_identifier"].input_schema["properties"].keys()

        check = await session.call_tool(
            "check_message", {"text": "Guaranteed 5% daily profit, pay to rajesh@okaxis today only"}
        )
        verdict = _data(check)
        assert verdict["level"] in ("HIGH_RISK", "SUSPICIOUS"), verdict
        assert isinstance(verdict["reasons"], list) and verdict["reasons"]

        lookup = await session.call_tool("search_sebi_register", {"name": "zerodha"})
        reg = _data(lookup)
        assert reg["name"] == "zerodha"
        assert isinstance(reg["candidates"], list)
