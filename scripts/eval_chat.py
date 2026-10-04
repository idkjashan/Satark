"""Evaluate the chat (Track C) on tests/golden/chat_v1.yaml: scope decisions, required content, guards.

    SATARK_LLM=local:qwen2.5:3b-instruct SATARK_LLM_BASE_URL=http://<ollama>:11434/v1 \
        uv run python scripts/eval_chat.py [--json out.json]

Each question runs as a fresh chat (no checked message). A reply passes when its `refused` flag is what the set
expects, it contains one of `must_any`, none of `must_not`, and the app's own output guards find no problem.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import yaml

from satark.config import Settings
from satark.harness import guards
from satark.harness.runtime import build_runtime, close_runtime

SET = Path(__file__).resolve().parent.parent / "tests" / "golden" / "chat_v1.yaml"


async def run_one(rt, item: dict) -> dict:
    t0 = time.monotonic()
    h = await rt.orchestrator.start_chat(None, item["message"], None, item.get("lang", "en"), False)
    out = {"text": "", "refused": None, "fallback": False, "tools": []}
    async for ev in rt.bus.subscribe(h.run_id):
        if ev.type == "answer":
            out.update(text=ev.data["text"], refused=ev.data.get("refused"), fallback=ev.data.get("fallback_used"))
        elif ev.type == "tool_status" and ev.data.get("status") == "start":
            out["tools"].append(ev.data.get("label") or ev.data.get("tool"))
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


def grade(item: dict, out: dict, config, case) -> list[str]:
    exp, text = item["expect"], out["text"].lower()
    problems = []
    if out["refused"] != exp.get("refused"):
        problems.append(f"refused={out['refused']} (want {exp.get('refused')})")
    if exp.get("must_any") and not any(w.lower() in text for w in exp["must_any"]):
        problems.append("missing required content")
    if any(w.lower() in text for w in exp.get("must_not", [])):
        problems.append("contains forbidden content")
    bad = [p for p in guards.check_output(out["text"], case, config, item.get("lang", "en"), max_words=200)
           if p not in ("grounding",)]
    if bad:
        problems.append(f"guards: {bad}")
    return problems


async def evaluate(items: list[dict]) -> list[tuple[dict, dict, list[str]]]:
    env = {k: v for k, v in os.environ.items() if k.startswith("SATARK_")}
    rt = await build_runtime(Settings.from_env(network=False, env=env))
    print("AI roles:", rt.router.status())
    rows = []
    for item in items:
        out = await run_one(rt, item)
        case = rt.orchestrator.cases.new(lang=item.get("lang", "en"), simple=False)
        problems = grade(item, out, rt.config, case)
        rows.append((item, out, problems))
        print(f"{'ok' if not problems else 'XX'} {item['id']} {out['seconds']}s refused={out['refused']}"
              f"{' (fallback)' if out['fallback'] else ''} {'; '.join(problems)} | {out['text'][:110]!r}")
    await close_runtime(rt)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = asyncio.run(evaluate(yaml.safe_load(SET.read_text(encoding="utf-8"))))
    passed = sum(not p for _, _, p in rows)
    secs = sorted(o["seconds"] for _, o, _ in rows)
    print(f"\npassed {passed}/{len(rows)} · fallback answers {sum(o['fallback'] for _, o, _ in rows)}"
          f" · median {secs[len(secs) // 2]}s · max {secs[-1]}s")
    if a.json:
        Path(a.json).write_text(json.dumps([{"id": i["id"], **o, "problems": p} for i, o, p in rows], indent=1,
                                           ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
