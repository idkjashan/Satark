"""Evaluate the screenshot path on tests/fixtures/screens (OCR, optional vision model, rules, AI review).

    uv run python scripts/eval_screens.py                                   # on-server OCR + rules only
    SATARK_LLM_IMAGE=local:minicpm-v:8b SATARK_LLM=local:qwen2.5:3b-instruct \
    SATARK_LLM_BASE_URL=http://<ollama>:11434/v1 uv run python scripts/eval_screens.py --json out.json

For each image: were the identifiers drawn in it extracted exactly (UPI IDs, phones, links), and is the verdict
right (scam -> High risk or Suspicious; genuine -> neither)?
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path

import yaml

from satark.config import Settings
from satark.harness.orchestrator import CheckInput
from satark.harness.runtime import build_runtime, close_runtime

SCREENS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "screens"
CAUGHT = {"HIGH_RISK", "SUSPICIOUS"}


def _norm_id(v: str) -> str:
    return re.sub(r"[\s\-()]", "", v.lower()).removeprefix("https://").removeprefix("http://").removeprefix("www.")


async def run_one(rt, item: dict, limit_s: float) -> dict:
    t0 = time.monotonic()
    image = (SCREENS / item["file"]).read_bytes()
    h = await rt.orchestrator.start_check(CheckInput(image=image, image_mime="image/png", lang=item.get("lang", "en")))
    out = {"level": None, "ai": False, "reading": None, "entities": []}

    async def consume() -> None:
        async for ev in rt.bus.subscribe(h.run_id):
            if ev.type == "verdict":
                out["level"], out["ai"] = ev.data["level"], bool(ev.data.get("ai_reviewed"))
            elif ev.type == "image_reading":
                out["reading"] = ev.data
            elif ev.type == "entities":
                out["entities"] = [e["display"] for e in ev.data["items"] if e["type"] in ("upi.vpa", "phone", "url", "domain")]

    try:
        await asyncio.wait_for(consume(), timeout=limit_s)
    except TimeoutError:
        out["level"] = out["level"] or "TIMEOUT"
    found = {_norm_id(e) for e in out["entities"]}
    wanted = [_norm_id(i) for i in item.get("identifiers", [])]
    out["ids_exact"] = sum(any(w == f or w in f for f in found) for w in wanted)
    out["ids_total"] = len(wanted)
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


async def evaluate(items: list[dict], limit_s: float) -> list[tuple[dict, dict]]:
    env = {k: v for k, v in os.environ.items() if k.startswith("SATARK_")}
    rt = await build_runtime(Settings.from_env(network=False, env=env))
    print("AI roles:", rt.router.status())
    rows = []
    for item in items:
        r = await run_one(rt, item, limit_s)
        rows.append((item, r))
        ok = (r["level"] in CAUGHT) == (item["expect"] == "scam")
        print(f"{'ok' if ok else 'XX'} {item['id']} {item['template']:<15} {item['lang']} {item['expect']:<5} -> {r['level']}"
              f"{' (AI)' if r['ai'] else ''} ids {r['ids_exact']}/{r['ids_total']} {r['seconds']}s"
              f"{' | ' + (r['reading'] or {}).get('screen', '') if r['reading'] else ''}")
    await close_runtime(rt)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args()
    items = yaml.safe_load((SCREENS / "manifest.yaml").read_text(encoding="utf-8"))
    rows = asyncio.run(evaluate(items, a.timeout))
    scams = [(i, r) for i, r in rows if i["expect"] == "scam"]
    legit = [(i, r) for i, r in rows if i["expect"] != "scam"]
    caught = sum(r["level"] in CAUGHT for _, r in scams)
    fa = sum(r["level"] in CAUGHT for _, r in legit)
    ids = sum(r["ids_exact"] for _, r in rows), sum(r["ids_total"] for _, r in rows)
    secs = sorted(r["seconds"] for _, r in rows)
    print(f"\nscams caught {caught}/{len(scams)} · false alarms {fa}/{len(legit)} · identifiers exact {ids[0]}/{ids[1]}"
          f" · AI-reviewed {sum(r['ai'] for _, r in rows)}/{len(rows)} · median {secs[len(secs) // 2]}s · max {secs[-1]}s")
    if a.json:
        Path(a.json).write_text(json.dumps([{"id": i["id"], **r} for i, r in rows], indent=1, ensure_ascii=False),
                                encoding="utf-8")


if __name__ == "__main__":
    main()
