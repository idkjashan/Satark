"""Evaluate a message set through the real harness, with or without the AI model.

    uv run python scripts/eval_set.py tests/golden/heldout_v3.yaml                 # rules only
    SATARK_LLM=local:qwen2.5:3b-instruct SATARK_LLM_BASE_URL=http://<ollama>:11434/v1 \
        uv run python scripts/eval_set.py tests/golden/heldout_v3.yaml --json out.json

Accepts both formats: golden cases (expect.level) and blind sets (expect.verdict scam|legit).
Scam "caught" = HIGH_RISK or SUSPICIOUS; legit "false alarm" = HIGH_RISK or SUSPICIOUS.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

import yaml

from satark.config import Settings
from satark.harness.orchestrator import CheckInput
from satark.harness.runtime import build_runtime, close_runtime

CAUGHT = {"HIGH_RISK", "SUSPICIOUS"}


def is_message(case: dict) -> bool:
    """Items with a `form` (narrative, awareness) are stories about scams, not messages to check."""
    return not case.get("form")


def recognised(case: dict, r: dict) -> bool:
    """A narrative/awareness item passes on the about-a-scam marker or, for a scam narrative, a SUSPICIOUS/HIGH_RISK
    level; a legit awareness post must never be SUSPICIOUS/HIGH_RISK."""
    caught = r["level"] in CAUGHT
    return (r["about_scam"] or caught) if is_scam(case) else (r["about_scam"] and not caught)


def is_scam(case: dict) -> bool:
    exp = case.get("expect", {})
    if "verdict" in exp:
        return exp["verdict"] == "scam"
    return exp.get("level") in CAUGHT


async def run_one(rt, case: dict, limit_s: float) -> dict:
    t0 = time.monotonic()
    h = await rt.orchestrator.start_check(CheckInput(text=case["text"], lang=case.get("lang", "en")))
    out = {"level": None, "about_scam": False, "codes": [], "ai": False, "answered": False, "error": None}

    async def consume() -> None:
        async for ev in rt.bus.subscribe(h.run_id):
            if ev.type == "verdict":
                out["level"], out["ai"] = ev.data["level"], bool(ev.data.get("ai_reviewed"))
                out["about_scam"] = bool(ev.data.get("about_scam"))
            elif ev.type == "check_result":
                out["codes"] += [c for c in ev.data["signals"] if c not in out["codes"]]
            elif ev.type == "answer":
                out["answered"] = True
            elif ev.type == "error":
                out["error"] = ev.data.get("code")

    try:
        await asyncio.wait_for(consume(), timeout=limit_s)
    except TimeoutError:
        out["error"] = "timeout"
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


async def evaluate(cases: list[dict], limit_s: float, network: bool = False) -> list[tuple[dict, dict]]:
    env = {k: v for k, v in os.environ.items() if k.startswith("SATARK_")}
    rt = await build_runtime(Settings.from_env(network=network, env=env))
    print("AI roles:", rt.router.status(), "tools:", rt.tools.status() if rt.tools else None)
    rows = []
    for c in cases:
        r = await run_one(rt, c, limit_s)
        rows.append((c, r))
        mark = ("ok" if (r["level"] in CAUGHT) == is_scam(c) else "XX") if is_message(c) else (
            "ok" if recognised(c, r) else "XX")
        print(f"{mark} {c['id']:<22} {'scam ' if is_scam(c) else 'legit'} -> {r['level']}{' (AI)' if r['ai'] else ''}"
              f"{' answered' if r['answered'] else ''} {r['seconds']}s {r['codes'][:6]}")
    await close_runtime(rt)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--network", action="store_true", help="live lookups and web search on (slower, not repeatable)")
    a = ap.parse_args()
    rows = asyncio.run(evaluate(yaml.safe_load(Path(a.path).read_text(encoding="utf-8")), a.timeout, a.network))
    stories = [(c, r) for c, r in rows if not is_message(c)]
    rows = [(c, r) for c, r in rows if is_message(c)]  # the metrics below are over messages only
    scams = [(c, r) for c, r in rows if is_scam(c)]
    legit = [(c, r) for c, r in rows if not is_scam(c)]
    caught = sum(r["level"] in CAUGHT for _, r in scams)
    high = sum(r["level"] == "HIGH_RISK" for _, r in scams)
    fa = sum(r["level"] in CAUGHT for _, r in legit)
    secs = sorted(r["seconds"] for _, r in rows) or [0]
    print(f"\nscams caught {caught}/{len(scams)} = {caught / max(1, len(scams)):.1%} · HIGH_RISK {high}/{len(scams)}"
          f" · false alarms {fa}/{len(legit)} = {fa / max(1, len(legit)):.1%}")
    print(f"AI-reviewed {sum(r['ai'] for _, r in rows)}/{len(rows)} · errors {Counter(r['error'] for _, r in rows if r['error'])}"
          f" · median {secs[len(secs) // 2]}s · max {secs[-1]}s")
    print(f"narratives/awareness recognised as about-a-scam: {sum(recognised(c, r) for c, r in stories)}/{len(stories)}")
    if a.json:
        out = [{"id": c["id"], "scam": is_scam(c), "form": c.get("form"), **r} for c, r in rows + stories]
        Path(a.json).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
