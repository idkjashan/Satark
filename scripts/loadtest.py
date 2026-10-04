"""Concurrent-check load test against a running server (LLD §26.1 "Load").

    uv run python scripts/loadtest.py [--base http://127.0.0.1:8000] [-n 50] [--json out.json]

Run the server with SATARK_RATE_LIMIT_SCALE=0 (and SATARK_OFFLINE=1 to measure the harness
without outside services). Reports time to the verdict event and to done, p50/p95/max.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import httpx

MESSAGES = [
    ("en", "Guaranteed 3% daily returns! Join VIP group, pay ₹5,000 to profit.king@ybl now. Limited seats."),
    ("hi", "सेबी रजिस्टर्ड सलाहकार, रोज़ 5% पक्का मुनाफा। अभी जुड़ें, सीमित सीटें। UPI: lakshmi.trade@okaxis"),
    ("en", "Withdrawal blocked. Pay 18% tax (₹12,600) to unlock your ₹70,000 profit. Download https://bit.ly/3xYzAbc"),
    ("en", "Your SIP of ₹5,000 is due on 5 Oct. Never share your OTP with anyone. - Example AMC"),
    ("hi", "आपका सिम बंद हो जाएगा, CBI केस दर्ज है, वीडियो कॉल पर रहें। अभी +92 300 1234567 पर कॉल करें"),
]


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


async def one(client: httpx.AsyncClient, i: int) -> dict:
    lang, text = MESSAGES[i % len(MESSAGES)]
    t0 = time.monotonic()
    r = await client.post("/v1/checks", data={"text": text, "lang": lang, "client": "test"})
    if r.status_code != 202:
        return {"ok": False, "status": r.status_code}
    url = r.json()["events_url"]
    verdict_s = done_s = None
    level = None
    async with client.stream("GET", url, headers={"Accept": "text/event-stream"}, timeout=60) as s:
        event = None
        async for line in s.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event == "verdict":
                verdict_s = time.monotonic() - t0
                level = json.loads(line[5:]).get("level")
            elif line.startswith("data:") and event in ("done", "error"):
                done_s = time.monotonic() - t0
                return {"ok": event == "done", "verdict_s": verdict_s, "done_s": done_s, "level": level}
    return {"ok": False, "status": "stream ended early"}


async def main_async(base: str, n: int) -> dict:
    limits = httpx.Limits(max_connections=n * 2, max_keepalive_connections=n * 2)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as client:
        t0 = time.monotonic()
        res = await asyncio.gather(*(one(client, i) for i in range(n)), return_exceptions=True)
        wall = time.monotonic() - t0
    good = [r for r in res if isinstance(r, dict) and r.get("ok")]
    v = [r["verdict_s"] for r in good if r.get("verdict_s") is not None]
    d = [r["done_s"] for r in good]
    return {
        "requests": n, "ok": len(good), "errors": n - len(good), "wall_s": round(wall, 2),
        "verdict_p50_s": round(pct(v, 50), 3), "verdict_p95_s": round(pct(v, 95), 3), "verdict_max_s": round(max(v or [0]), 3),
        "done_p50_s": round(pct(d, 50), 3), "done_p95_s": round(pct(d, 95), 3),
        "mean_verdict_s": round(statistics.mean(v), 3) if v else None,
        "levels": {lvl: sum(1 for r in good if r.get("level") == lvl) for lvl in {r.get("level") for r in good}},
        "failures": [r if isinstance(r, dict) else repr(r) for r in res if not (isinstance(r, dict) and r.get("ok"))][:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--json")
    a = ap.parse_args()
    out = asyncio.run(main_async(a.base, a.n))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
    return 0 if out["errors"] == 0 and out["verdict_p95_s"] < 10 else 1


if __name__ == "__main__":
    sys.exit(main())
