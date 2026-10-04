"""Chrome UX Report India top list -> popularity (registrable domain -> smallest rank bucket)."""

from __future__ import annotations

import csv
import gzip
import re
from pathlib import Path

import yaml

from satark.infra.norm import registrable_domain
from satark.ingest.gate import SourceResult, sha256_file


def _as_on(path: Path, default: str = "2026-10-03") -> str:
    sidecar = path.with_suffix(path.suffix + ".meta.yaml")
    if sidecar.exists():
        return yaml.safe_load(sidecar.read_text()).get("as_on", default)
    return default


def load(spec: dict) -> SourceResult:
    path = Path(spec["_root"]) / spec["path"]
    pattern = re.compile(spec["gates"]["key_pattern"])

    buckets: dict[str, int] = {}
    total = matched = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            total += 1
            try:
                rank = int(rec.get("rank") or 0)
            except ValueError:
                continue
            domain = registrable_domain((rec.get("origin") or "").strip())
            if not domain or not pattern.match(domain):
                continue
            matched += 1
            if domain not in buckets or rank < buckets[domain]:
                buckets[domain] = rank

    rows = list(buckets.items())
    return SourceResult(rows=rows, total=total, matched=matched, as_on=_as_on(path), sha256=sha256_file(path))
