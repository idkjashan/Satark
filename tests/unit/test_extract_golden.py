"""Golden-string runner for tests/golden/entities.yaml (CONTRACTS §8, LLD build step 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from satark.harness.extract.pipeline import ExtractorPipeline

GOLDEN = yaml.safe_load((Path(__file__).resolve().parents[1] / "golden" / "entities.yaml").read_text())

POSITIVE_CASES = [(t, s) for t, spec in GOLDEN.items() for s in spec["positive"]]
NEGATIVE_CASES = [(t, s) for t, spec in GOLDEN.items() for s in spec["negative"]]


@pytest.fixture()
def pipeline(config):
    return ExtractorPipeline(config)


def test_golden_file_has_minimum_examples():
    for t, spec in GOLDEN.items():
        assert len(spec["positive"]) >= 3, f"{t}: need >=3 positive examples"
        assert len(spec["negative"]) >= 2, f"{t}: need >=2 negative examples"


@pytest.mark.parametrize(("entity_type", "text"), POSITIVE_CASES, ids=[f"{t}:{s[:30]}" for t, s in POSITIVE_CASES])
def test_golden_positive(pipeline, make_case, entity_type, text):
    case = make_case()
    pipeline.regex(case, text)
    hits = [e for e in case.entities if e.type == entity_type]
    assert hits, f"expected a {entity_type} entity in {text!r}"


@pytest.mark.parametrize(("entity_type", "text"), NEGATIVE_CASES, ids=[f"{t}:{s[:30]}" for t, s in NEGATIVE_CASES])
def test_golden_negative(pipeline, make_case, entity_type, text):
    case = make_case()
    pipeline.regex(case, text)
    hits = [e for e in case.entities if e.type == entity_type]
    assert not hits, f"did not expect a {entity_type} entity in {text!r}"
