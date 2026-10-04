"""Scope router (satark/harness/scope_router.py): the decision rule in isolation (a fake
encoder, no fastembed, no network), plus one smoke test against the real encoder/config if it
loads in this environment.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from satark.config import ROOT
from satark.harness.scope_router import ScopeRouter, load_encoder


class _FakeEncoder:
    """Deterministic 2-D "embeddings": one axis per topic, so the test controls similarity
    directly instead of depending on a real model's numbers."""

    def __init__(self, vec_by_text: dict[str, list[float]]) -> None:
        self.vec_by_text = vec_by_text

    def embed(self, texts: list[str]):
        return [np.array(self.vec_by_text[t]) for t in texts]


def _router(vec_by_text: dict[str, list[float]], routes: dict[str, list[str]], **kw) -> ScopeRouter:
    encoder = _FakeEncoder(vec_by_text)
    route_vecs = {name: np.array([vec_by_text[u] for u in us]) for name, us in routes.items()}
    # build() would normalise too; vectors below are already unit length for a readable test
    return ScopeRouter(route_vecs=route_vecs, encoder=encoder, **kw)


def test_closest_route_wins_above_threshold():
    vecs = {"money q": [1.0, 0.0], "money route": [1.0, 0.0], "off route": [0.0, 1.0]}
    router = _router(vecs, {"money_or_scam_question": ["money route"], "off_topic": ["off route"]})
    assert router.classify("money q") == "money_or_scam_question"


def test_below_threshold_falls_back_to_none():
    vecs = {"vague q": [0.1, 0.1], "money route": [1.0, 0.0], "off route": [0.0, 1.0]}
    norm = np.linalg.norm(vecs["vague q"])
    vecs["vague q"] = [v / norm for v in vecs["vague q"]]
    router = _router(vecs, {"money_or_scam_question": ["money route"], "off_topic": ["off route"]}, threshold=0.3)
    assert router.classify("vague q") is None


def test_close_top_two_routes_fall_back_to_none():
    """A query almost exactly between two routes' best examples is "too close to call", even
    though both are above threshold."""
    a = np.array([1.0, 0.0])
    b = np.array([0.6, 0.8])  # unit length, ~53 degrees from a
    q = a + b
    q = q / np.linalg.norm(q)
    vecs = {"q": q.tolist(), "route a": a.tolist(), "route b": b.tolist()}
    router = _router(vecs, {"money_or_scam_question": ["route a"], "stock_tip_request": ["route b"]},
                     threshold=0.3, margin=0.2)
    assert router.classify("q") is None


def test_nearest_neighbour_not_average_lets_one_good_example_win():
    """One route has a so-so example everywhere; the other has one dead-on example. Nearest
    neighbour (max per route) should pick the dead-on one even if a mean would not."""
    q = [1.0, 0.0]
    vecs = {
        "q": q,
        "exact": [1.0, 0.0],
        "poor1": [0.0, 1.0],
        "poor2": [-0.9, 0.1],
    }
    router = _router(vecs, {"stock_tip_request": ["exact"], "money_or_scam_question": ["poor1", "poor2"]})
    assert router.classify("q") == "stock_tip_request"


def test_disabled_when_no_encoder():
    router = ScopeRouter()
    assert not router.enabled()
    assert router.classify("anything") is None


def test_empty_text_is_none():
    router = _router({"x": [1.0, 0.0]}, {"money_or_scam_question": ["x"]})
    assert router.classify("   ") is None


async def test_classify_async_matches_classify():
    vecs = {"q": [1.0, 0.0], "r": [1.0, 0.0]}
    router = _router(vecs, {"money_or_scam_question": ["r"]})
    assert await router.classify_async("q") == router.classify("q")


# ---- real encoder + the shipped config/routes.yaml (skipped if the model can't load here) ----

_encoder = load_encoder()


@pytest.mark.skipif(_encoder is None, reason="fastembed model not available in this environment")
def test_real_router_separates_scam_question_from_stock_tip_and_off_topic():
    router = ScopeRouter.build(ROOT / "config" / "routes.yaml", _encoder)
    assert router.enabled()
    assert router.classify("How do I check if a trading app is registered with SEBI?") == "money_or_scam_question"
    assert router.classify("Which penny stock should I buy tomorrow for a quick profit?") == "stock_tip_request"
    assert router.classify("Write a haiku about the rain") == "off_topic"


@pytest.mark.skipif(_encoder is None, reason="fastembed model not available in this environment")
def test_real_router_utterances_are_not_the_golden_set(tmp_path: Path):
    """config/routes.yaml must not just be tests/golden/chat_v1.yaml's questions copy-pasted in
    (that would score the router on its own answer key)."""
    import yaml

    golden_messages = {
        item["message"].strip().lower()
        for item in yaml.safe_load((ROOT / "tests" / "golden" / "chat_v1.yaml").read_text(encoding="utf-8"))
    }
    routes = yaml.safe_load((ROOT / "config" / "routes.yaml").read_text(encoding="utf-8"))["routes"]
    utterances = {u.strip().lower() for us in routes.values() for u in us}
    assert not (golden_messages & utterances)
