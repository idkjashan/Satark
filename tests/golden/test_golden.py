"""Golden evaluation: every message in tests/golden/cases.yaml through the real harness (offline, fixture DB).

Each case asserts its expected level and reason codes. `uv run python -m tests.golden.test_golden`
prints the evaluation summary (recall on HIGH_RISK, false alarms on legitimate messages).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

CASES_FILE = Path(__file__).with_name("cases.yaml")
CASES = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8")) if CASES_FILE.exists() else []


async def run_case(rt, text: str, lang: str) -> dict:
    """Run one check; return the verdict payload and every signal code seen."""
    from satark.harness.orchestrator import CheckInput

    handle = await rt.orchestrator.start_check(CheckInput(text=text, lang=lang, client="test"))
    verdict, codes, events = None, set(), []
    async for ev in rt.bus.subscribe(handle.run_id):
        events.append(ev.type)
        if ev.type == "check_result":
            codes.update(ev.data.get("signals", []))
        elif ev.type == "verdict":
            verdict = ev.data
    return {"verdict": verdict or {}, "codes": codes, "events": events}


@pytest.fixture()
async def runtime(settings):
    rt_mod = pytest.importorskip("satark.harness.runtime")
    rt = await rt_mod.build_runtime(settings)
    yield rt
    await rt_mod.close_runtime(rt)


@pytest.mark.skipif(not CASES, reason="no golden cases yet")
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES] if CASES else None)
async def test_golden_case(runtime, case):
    if case.get("requires_llm") and not runtime.router.enabled("extract"):
        pytest.skip("needs the AI model (set SATARK_LLM); the offline run has none")
    out = await run_case(runtime, case["text"], case.get("lang", "en"))
    exp = case["expect"]
    level = out["verdict"].get("level")
    codes = out["codes"]
    assert out["events"][-1] == "done", out["events"]
    assert level == exp["level"], f"{case['id']}: level {level} != {exp['level']}; codes {sorted(codes)}"
    if exp.get("codes_any"):
        assert codes & set(exp["codes_any"]), f"{case['id']}: none of {exp['codes_any']} in {sorted(codes)}"
    for c in exp.get("codes_all", []) or []:
        assert c in codes, f"{case['id']}: missing {c}; got {sorted(codes)}"
    bad = codes & set(exp.get("codes_none", []) or [])
    assert not bad, f"{case['id']}: unexpected {sorted(bad)}"


async def _summary() -> None:  # pragma: no cover - manual report
    import tempfile

    from satark.harness.runtime import build_runtime, close_runtime

    from satark.config import Settings
    from tests.fixtures.fixture_db import build_fixture_db

    db = build_fixture_db(Path(tempfile.mkdtemp()) / "registry.db")
    import os

    env = {k: v for k, v in os.environ.items() if k.startswith("SATARK_LLM")} | {"SATARK_RATE_LIMIT_SCALE": "0"}
    rt = await build_runtime(Settings.from_env(db_path=db, network=False, env=env))
    rows = []
    for c in CASES:
        if c.get("requires_llm") and not rt.router.enabled("extract"):
            continue
        out = await run_case(rt, c["text"], c.get("lang", "en"))
        rows.append((c, out["verdict"].get("level"), out["codes"]))
    await close_runtime(rt)
    scams = [r for r in rows if r[0]["expect"]["level"] != "NO_SIGNS"]
    legit = [r for r in rows if r[0]["expect"]["level"] == "NO_SIGNS"]
    exact = sum(r[1] == r[0]["expect"]["level"] for r in rows)
    flagged = sum(r[1] in ("HIGH_RISK", "SUSPICIOUS") for r in scams)
    high_exp = [r for r in rows if r[0]["expect"]["level"] == "HIGH_RISK"]
    high_hit = sum(r[1] == "HIGH_RISK" for r in high_exp)
    false_alarm = sum(r[1] in ("HIGH_RISK", "SUSPICIOUS") for r in legit)
    print(f"cases {len(rows)} · exact level {exact}/{len(rows)}")
    print(f"scams flagged (HIGH or SUSPICIOUS) {flagged}/{len(scams)} · HIGH_RISK recall {high_hit}/{len(high_exp)}")
    print(f"false alarms on legitimate messages {false_alarm}/{len(legit)}")
    for c, lvl, codes in rows:
        if lvl != c["expect"]["level"]:
            print(f"  MISMATCH {c['id']}: got {lvl}, expected {c['expect']['level']}; codes {sorted(codes)}")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_summary())
