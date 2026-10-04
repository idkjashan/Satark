"""satark.ingest.crux against a tiny hand-built gzip CSV (no need for the real ~8 MB snapshot)."""

from __future__ import annotations

import csv
import gzip
import io

from satark.ingest.crux import load


def _make_gz(tmp_path, rows: list[tuple[str, int]]):
    path = tmp_path / "tiny_crux.csv.gz"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["origin", "rank"])
    writer.writerows(rows)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(buf.getvalue())
    return path


def test_load_keeps_the_smallest_bucket_per_registrable_domain(tmp_path):
    _make_gz(
        tmp_path,
        [
            ("https://kite.zerodha.com", 1000),
            ("https://zerodha.com", 5000),  # same registrable domain, worse (larger) rank
            ("https://groww.in", 1000),
            ("not a url", 1000),  # dropped: no usable domain
        ],
    )
    result = load({"_root": tmp_path, "path": "tiny_crux.csv.gz", "gates": {"key_pattern": r"^[a-z0-9.-]+\.[a-z]{2,}$"}})
    rows = dict(result.rows)
    assert rows["zerodha.com"] == 1000  # the smaller (better) of 1000 and 5000
    assert rows["groww.in"] == 1000
    assert result.total == 4
    assert result.matched == 3


def test_load_reads_as_on_from_the_meta_sidecar(tmp_path):
    path = _make_gz(tmp_path, [("https://example.in", 1000)])
    (tmp_path / (path.name + ".meta.yaml")).write_text("as_on: '2026-08-31'\n")
    result = load({"_root": tmp_path, "path": "tiny_crux.csv.gz", "gates": {"key_pattern": r"^[a-z0-9.-]+\.[a-z]{2,}$"}})
    assert result.as_on == "2026-08-31"
