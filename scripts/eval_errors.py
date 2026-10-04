"""Where the harness is wrong: group the misses and false alarms of eval_set.py runs by type and language.

    uv run python scripts/eval_errors.py tests/golden/heldout_v3.yaml run.json [other_run.json ...]

With two or more runs of the same set it also lists the messages whose result changed between runs (what a
change fixed and what it broke).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

CAUGHT = {"HIGH_RISK", "SUSPICIOUS"}


def main() -> None:
    cases = {c["id"]: c for c in yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))}
    runs = [(Path(p).stem, {r["id"]: r for r in json.loads(Path(p).read_text(encoding="utf-8"))}) for p in sys.argv[2:]]
    for name, rows in runs:
        stories = {i: r for i, r in rows.items() if r.get("form")}  # narratives/awareness: judged by the about-a-scam marker
        rows = {i: r for i, r in rows.items() if i not in stories}
        wrong = [(i, r) for i, r in rows.items() if (r["level"] in CAUGHT) != r["scam"]]
        by_kind: dict[str, list[str]] = defaultdict(list)
        for i, r in wrong:
            c = cases[i]
            kind = "MISS" if r["scam"] else "FALSE ALARM"
            by_kind[f"{kind} {c.get('lang')} {c.get('type', '')}"].append(f"{i}->{r['level']}")
        secs = sorted(r["seconds"] for r in rows.values())
        print(f"== {name}: {len(wrong)} wrong of {len(rows)}; median {secs[len(secs) // 2]}s, p90 "
              f"{secs[int(len(secs) * 0.9)]}s; levels {dict(Counter(r['level'] for r in rows.values()))}")
        for key in sorted(by_kind):
            print(f"   {key}: {', '.join(by_kind[key])}")
        if stories:
            bad = [i for i, r in stories.items() if not ((r.get("about_scam") or r["level"] in CAUGHT) if r["scam"]
                                                         else (r.get("about_scam") and r["level"] not in CAUGHT))]
            print(f"   narratives/awareness not recognised: {len(bad)}/{len(stories)} {', '.join(bad)}")
    if len(runs) > 1:
        (a, ra), (b, rb) = runs[0], runs[-1]
        print(f"== changed between {a} and {b}:")
        for i in ra:
            if i in rb and not ra[i].get("form") and (ra[i]["level"] in CAUGHT) != (rb[i]["level"] in CAUGHT):
                fixed = (rb[i]["level"] in CAUGHT) == rb[i]["scam"]
                print(f"   {'FIXED' if fixed else 'BROKE'} {i} ({'scam' if ra[i]['scam'] else 'legit'}): "
                      f"{ra[i]['level']} -> {rb[i]['level']} | {cases[i]['text'][:90]!r}")


if __name__ == "__main__":
    main()
