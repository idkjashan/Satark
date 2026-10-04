"""`python -m satark.check "<text>" [--lang hi] [--qr ...] [--offline]` (CONTRACTS §5).

Builds the runtime, starts one check, and prints every event as one JSON line to stdout -
no server needed. Exits 0 once the run emits `done` or `error`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from satark.config import Settings
from satark.harness.orchestrator import CheckInput
from satark.harness.runtime import build_runtime, close_runtime


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m satark.check")
    parser.add_argument("text", nargs="?", default=None)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--qr", default=None)
    parser.add_argument("--simple", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.offline:
        env["SATARK_OFFLINE"] = "1"
    settings = Settings.from_env(env=env, network=not args.offline)

    rt = await build_runtime(settings)
    try:
        handle = await rt.orchestrator.start_check(
            CheckInput(text=args.text, qr=args.qr, lang=args.lang, simple=args.simple)
        )
        async for event in rt.bus.subscribe(handle.run_id):
            print(json.dumps({"id": event.id, "event": event.type, "data": event.data}, ensure_ascii=False))
    finally:
        await close_runtime(rt)
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
