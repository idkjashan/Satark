"""satark.ingest.curated: official domains (brands.yaml + CSV), caution entries, PSP handles.

Runs against the tiny fixtures in tests/fixtures/ingest/, and once against the real curated
files Satark ships in data/manual/ to make sure those actually parse.
"""

from __future__ import annotations

from pathlib import Path

from satark.ingest.curated import load_caution_entries, load_official_domains, load_psp_handles

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "ingest"

_DOMAIN_PATTERN = r"^[a-z0-9.-]+\.[a-z]{2,}$"


def test_load_official_domains_merges_brands_and_csv_and_dedupes():
    spec = {
        "_root": FIXTURES,
        "path": "official_domains_sample.csv",
        "extra": "brands_sample.yaml",
        "gates": {"key_pattern": _DOMAIN_PATTERN},
    }
    result = load_official_domains(spec)
    by_domain = {r[0]: r for r in result.rows}
    assert by_domain["sampleregulator.gov.in"][1:3] == ("Sample Regulator", "regulator")
    # both domains in brands_sample.yaml normalise to the same registrable domain: one row, not two
    assert by_domain["samplebroker.com"][3] == "samplebroker"  # brand_id set for a brands.yaml row
    assert by_domain["examplemf.com"][1:3] == ("Example Mutual Fund", "amc")
    assert by_domain["examplemf.com"][3] is None  # no brand_id for a CSV-sourced row
    assert "not a domain" not in by_domain
    assert result.total > result.matched  # the CSV's bad row was counted and dropped


def test_load_official_domains_on_the_real_shipped_files():
    spec = {
        "_root": ROOT,
        "path": "data/manual/official_domains.csv",
        "extra": "config/brands.yaml",
        "gates": {"key_pattern": _DOMAIN_PATTERN},
    }
    result = load_official_domains(spec)
    domains = {r[0] for r in result.rows}
    assert "sebi.gov.in" in domains  # from brands.yaml
    assert "hdfcfund.com" in domains  # from brands.yaml (amc)
    assert "ppfas.com" in domains  # hand-curated from the AMFI apps page
    assert result.matched / result.total > 0.99


def test_load_caution_entries_normalises_by_entry_type_and_drops_unknown_rows():
    spec = {"_root": FIXTURES, "path": "caution_entries_sample.csv"}
    result = load_caution_entries(spec)
    by_type = {r[1]: r for r in result.rows}
    assert by_type["name"][2] == "quick profit advisory"  # name_norm
    assert by_type["phone"][2] == "+919999900000"  # phone_norm (E.164)
    assert by_type["domain"][2] == "fake-sebi-refund.in"  # registrable_domain, scheme/path stripped
    assert by_type["upi"][2] == "scammer@ybl"  # upi_norm (lower-cased)
    assert len(result.rows) == 4  # bogus_type and the blank-value row are both dropped
    assert result.as_on  # the curation date from the sidecar (or the default), not a notice date


def test_load_caution_entries_on_the_real_shipped_file():
    spec = {"_root": ROOT, "path": "data/manual/caution_entries.csv"}
    result = load_caution_entries(spec)
    assert result.rows and result.matched == result.total  # every shipped row is valid
    assert all(r[5].startswith("https://") for r in result.rows)  # each row cites its official source
    assert result.as_on  # the curation date from the .meta.yaml sidecar


def test_load_psp_handles_lower_cases_and_drops_bad_rows():
    spec = {"_root": FIXTURES, "path": "psp_handles_sample.csv", "gates": {"key_pattern": r"^[a-z0-9]+$"}}
    result = load_psp_handles(spec)
    by_handle = {r[0]: r for r in result.rows}
    assert by_handle["okaxis"] == ("okaxis", "Axis Bank", "Google Pay")
    assert "bad handle!" not in by_handle and "Bad Handle!" not in by_handle
    assert "nobank" not in by_handle  # bank is required (schema NOT NULL)
    assert len(result.rows) == 2


def test_load_psp_handles_on_the_real_shipped_file():
    spec = {"_root": ROOT, "path": "data/manual/psp_handles.csv", "gates": {"key_pattern": r"^[a-z0-9]+$"}}
    result = load_psp_handles(spec)
    by_handle = {r[0]: r for r in result.rows}
    assert by_handle["validhdfc"] == ("validhdfc", "HDFC Bank", None)
    assert by_handle["ybl"][1:] == ("Yes Bank", "PhonePe")
    assert result.matched == result.total
