"""Satark web-search MCP server (stdio transport): one tool, public-web search only.

Run: python -m satark.mcp_servers.websearch

Backend is chosen by the SATARK_WEBSEARCH_BACKEND environment variable:
  - "ddgs" (default): real DuckDuckGo search via the installed `ddgs` package.
  - "fake": deterministic canned results, no network at all (used by tests).

Note on the installed SDK: `mcp` 2.x renamed `FastMCP` to `MCPServer`
(`mcp.server.mcpserver.MCPServer`); `mcp.server.fastmcp` is a stub that only raises
`ModuleNotFoundError` pointing at the migration guide. `MCPServer` keeps the same
`@mcp.tool()` decorator and `.run("stdio")` entry point FastMCP v1 had.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from collections import OrderedDict

from mcp.server.mcpserver import MCPServer

log = logging.getLogger(__name__)

MAX_QUERY_LEN = 200
MAX_RESULTS_CAP = 8
TITLE_LEN = 120
SNIPPET_LEN = 300
CACHE_TTL_S = 3600.0
CACHE_MAX_ENTRIES = 256
BACKEND_TIMEOUT_S = 16.0

# Defense in depth: refuse anything that looks like it carries personal data, even though the
# tool description already tells the caller never to send it. Any single match refuses the
# whole query; which one matched only shapes the error message.
_PII_PATTERNS = (
    ("email address", re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")),
    ("UPI ID", re.compile(r"\S+@\S+")),  # catches handle-only ids too, e.g. "name@okaxis" (no dot)
    ("phone or account number", re.compile(r"(?:\d[ -]*){10,}")),  # 10+ digits; spaces/dashes don't break the run
    ("Aadhaar-like number", re.compile(r"\d{12}")),
    ("PAN", re.compile(r"[A-Z]{5}\d{4}[A-Z]")),
)


def _refusal(query: str) -> str | None:
    """None if `query` is safe to search; otherwise the reason it was refused."""
    if not query or not query.strip():
        return "empty query"
    if len(query) > MAX_QUERY_LEN:
        return f"query too long (max {MAX_QUERY_LEN} chars)"
    for label, pattern in _PII_PATTERNS:
        if pattern.search(query):
            return f"query refused: looks like it contains a {label}"
    return None


# ---- in-process cache: (normalised query, max_results) -> results, 1h TTL, capped size ----
_cache: OrderedDict[tuple[str, int], tuple[float, list[dict]]] = OrderedDict()


def _cache_get(key: tuple[str, int]) -> list[dict] | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, results = hit
    if time.monotonic() > expires_at:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return results


def _cache_put(key: tuple[str, int], results: list[dict]) -> None:
    _cache[key] = (time.monotonic() + CACHE_TTL_S, results)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)  # oldest first in (FIFO is enough for a size cap)


def _trim(title: str, url: str, snippet: str) -> dict:
    return {"title": (title or "")[:TITLE_LEN], "url": url or "", "snippet": (snippet or "")[:SNIPPET_LEN]}


def _fake_backend(query: str, n: int) -> list[dict]:
    """Deterministic, no network: two results naming the query, plus a 'scam' hit if it says so."""
    out = [
        _trim(f"{query} - official information", "https://example.com/1", f"General information about {query}."),
        _trim(f"{query} - news and reviews", "https://example.com/2", f"Recent coverage of {query}."),
    ]
    if "scam" in query.lower():
        out.append(_trim(f"{query} – reported as a scam (example)", "https://example.com/3", "Reported as a scam."))
    return out[:n]


# Search engines rate-limit scrapers, so try a few in order and stop at the first that answers.
_ENGINES = tuple(os.environ.get("SATARK_WEBSEARCH_ENGINES", "duckduckgo,yahoo,mojeek,brave").split(","))


def _ddgs_backend(query: str, n: int) -> list[dict]:
    from ddgs import DDGS  # imported lazily: the fake backend must work with no network at all
    from ddgs.exceptions import DDGSException

    raw: list[dict] = []
    for engine in _ENGINES:
        try:
            with DDGS(timeout=4) as ddgs:
                raw = ddgs.text(query, region="in-en", safesearch="moderate", max_results=n, backend=engine.strip())
        except DDGSException:
            continue
        if raw:
            break
    return [_trim(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in raw[:n]]


def _run_backend(query: str, n: int) -> list[dict]:
    """Runs synchronously (blocking I/O for the real backend) - call this via a thread, not inline."""
    backend = os.environ.get("SATARK_WEBSEARCH_BACKEND", "ddgs")
    return _fake_backend(query, n) if backend == "fake" else _ddgs_backend(query, n)


mcp = MCPServer("satark-websearch")


@mcp.tool(
    description="Search the public web. Use for names of firms, apps, websites or scam types; "
    "never for personal data."
)
async def search(query: str, max_results: int = 5) -> dict:
    refusal = _refusal(query)
    if refusal:
        return {"query": query, "results": [], "error": refusal}

    n = max(1, min(int(max_results), MAX_RESULTS_CAP))
    key = (query.strip().lower(), n)
    cached = _cache_get(key)
    if cached is not None:
        return {"query": query, "results": cached, "error": None}

    try:
        results = await asyncio.wait_for(asyncio.to_thread(_run_backend, query, n), timeout=BACKEND_TIMEOUT_S)
    except TimeoutError:
        return {"query": query, "results": [], "error": "search timed out"}
    except Exception as e:  # network errors, rate limits, ddgs exceptions: never crash the server
        log.warning("search backend failed: %s", e)
        return {"query": query, "results": [], "error": f"search failed: {type(e).__name__}: {e}"}

    _cache_put(key, results)
    return {"query": query, "results": results, "error": None}


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the MCP channel; logs go to stderr
    logging.getLogger("ddgs").setLevel(logging.ERROR)  # it logs every engine request
    mcp.run("stdio")


if __name__ == "__main__":
    main()
