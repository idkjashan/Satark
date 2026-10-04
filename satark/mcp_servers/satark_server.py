"""Satark itself as an MCP server (stdio transport): any MCP client (Claude Desktop, Cursor,
another agent) can run a scam check through it.

Run: python -m satark.mcp_servers.satark_server

The app runtime (satark.harness.runtime.build_runtime) is built once, in the MCP lifespan hook:
entered on connect, before the first request, and closed on disconnect via close_runtime. That
hook is `mcp.server.mcpserver.MCPServer`'s `lifespan=` constructor argument (mcp 2.x; see
websearch.py's docstring for the FastMCP -> MCPServer rename). Settings.from_env() reads the
environment this subprocess was launched with (SATARK_OFFLINE, SATARK_LLM, SATARK_DB, ...) -
this server applies no overrides of its own, same as scripts/eval_set.py.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import Context, MCPServer

from satark.config import Settings
from satark.harness.orchestrator import CheckInput
from satark.harness.runtime import Runtime, build_runtime, close_runtime

log = logging.getLogger(__name__)

RUN_TIMEOUT_S = 60.0


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[Runtime]:
    rt = await build_runtime(Settings.from_env())
    try:
        yield rt
    finally:
        await close_runtime(rt)


mcp = MCPServer("satark", lifespan=_lifespan)


async def _run_check(rt: Runtime, text: str, lang: str) -> dict:
    """Starts one check and folds its events into the shape every tool here returns.

    `check_result` events update rules/signals internally (CONTRACTS §6.1); the public shape only
    needs the final `verdict` (level, confidence, reasons, worth_noting, ai_reviewed) and the
    `explanation` event's summary. Mirrors how scripts/eval_set.py consumes the same bus.
    """
    handle = await rt.orchestrator.start_check(CheckInput(text=text, lang=lang))
    state: dict = {
        "level": "UNKNOWN",
        "confidence": "NOT_SURE",
        "reasons": [],
        "worth_noting": [],
        "summary": "",
        "ai_reviewed": False,
    }

    async def consume() -> None:
        async for ev in rt.bus.subscribe(handle.run_id):
            if ev.type == "verdict":
                d = ev.data
                state["level"] = d["level"]
                state["confidence"] = d["confidence"]
                state["reasons"] = [{"code": r["code"], "title": r["title"]} for r in d["reasons"]]
                state["worth_noting"] = d["worth_noting"]
                state["ai_reviewed"] = bool(d.get("ai_reviewed", False))
            elif ev.type == "explanation":
                state["summary"] = ev.data.get("summary") or ""
            elif ev.type == "error":
                log.warning("check run %s failed: %s", handle.run_id, ev.data)

    try:
        await asyncio.wait_for(consume(), timeout=RUN_TIMEOUT_S)
    except TimeoutError:
        log.warning("check run %s did not finish within %ss", handle.run_id, RUN_TIMEOUT_S)
    return state


@mcp.tool(description="Run a full scam check on a message (or extracted screenshot text) and return its verdict.")
async def check_message(text: str, ctx: Context, lang: str = "en") -> dict:
    rt: Runtime = ctx.request_context.lifespan_context
    return await _run_check(rt, text, lang)


@mcp.tool(
    description="Run a scam check on a single identifier (e.g. a UPI ID, phone number or link), "
    "treated as the whole message."
)
async def check_identifier(kind: str, value: str, ctx: Context) -> dict:
    # `kind` ("upi", "link", "phone", ...) is caller-side labelling only: the same regex-driven
    # extraction check_message uses finds the identifier inside `value` regardless of its label.
    rt: Runtime = ctx.request_context.lifespan_context
    return await _run_check(rt, value, "en")


@mcp.tool(description="Search the SEBI intermediary registry by name; returns the closest matches.")
async def search_sebi_register(name: str, ctx: Context, category: str | None = None) -> dict:
    rt: Runtime = ctx.request_context.lifespan_context
    candidates = rt.orchestrator.responder._search_registry(name, category)  # noqa: SLF001 (same owner, see spec)
    return {"name": name, "candidates": candidates[:5]}


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the MCP channel; logs go to stderr
    mcp.run("stdio")


if __name__ == "__main__":
    main()
