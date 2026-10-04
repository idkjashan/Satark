"""Knowledge base (satark/harness/knowledge.py): chunking of Satark's own content, hybrid
search (BM25 + embedding, merged by reciprocal rank fusion) and the async wrappers.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from satark.config import ROOT
from satark.harness.knowledge import Chunk, KnowledgeBase
from satark.harness.scope_router import load_encoder


def _make_content(root: Path) -> None:
    content = root / "content"
    (content / "lessons").mkdir(parents=True)
    (content / "sims").mkdir(parents=True)
    (content / "faq.json").write_text(json.dumps({
        "intents": [
            {"id": "verify_adviser", "answer": {"en": "Check SEBI's own register for the adviser's number.",
                                                "hi": "SEBI के रजिस्टर में जाँचें।"}},
            {"id": "no_text", "answer": {"en": "", "hi": ""}},  # must be skipped: nothing to index
        ],
    }), encoding="utf-8")
    (content / "lessons" / "sebi-registration.json").write_text(json.dumps({
        "id": "sebi-registration",
        "steps": [
            {"text": {"en": "A SEBI registration number means a person passed exams.", "hi": "रजिस्ट्रेशन नंबर का मतलब।"}},
            {"text": {"en": "It never means a guaranteed return.", "hi": "इसका मतलब गारंटी नहीं।"}},
        ],
    }), encoding="utf-8")
    (content / "sims" / "S1.json").write_text(json.dumps({
        "id": "S1",
        "title": {"en": "The fake trading-app trap", "hi": "नकली ट्रेडिंग-ऐप का जाल"},
        "states": {
            "deposit": {"say": {"en": "Deposit 10000 to start trading.", "hi": ""}},
            "blocked": {"say": {"en": "Withdrawal blocked, pay 18% tax.", "hi": ""},
                       "reveal": {"en": "A fee to withdraw your own money is always a scam.", "hi": ""}},
        },
    }), encoding="utf-8")


@pytest.fixture()
def content_root(tmp_path: Path) -> Path:
    _make_content(tmp_path)
    return tmp_path


def test_build_without_encoder_still_indexes_bm25(content_root: Path):
    kb = KnowledgeBase.build(content_root, encoder=None)
    assert kb.enabled()
    ids = {c.id for c in kb.chunks}
    assert "faq:verify_adviser" in ids
    assert "lesson:sebi-registration:1" in ids and "lesson:sebi-registration:2" in ids
    assert "sim:S1" in ids
    assert "faq:no_text" not in ids  # empty answer: no chunk
    assert kb.encoder is None and kb.embeddings is None


def test_sim_chunk_folds_in_title_and_state_narration(content_root: Path):
    kb = KnowledgeBase.build(content_root, encoder=None)
    sim = next(c for c in kb.chunks if c.id == "sim:S1")
    assert "fake trading-app trap" in sim.rendered("en")
    assert "18% tax" in sim.rendered("en")
    assert "always a scam" in sim.rendered("en")


def test_bm25_only_search_finds_lexical_match(content_root: Path):
    kb = KnowledgeBase.build(content_root, encoder=None)
    hits = kb.search("is a SEBI registration number a guarantee of anything", k=2)
    assert hits and hits[0].source == "lesson"


def test_best_returns_none_when_nothing_indexed(tmp_path: Path):
    (tmp_path / "content").mkdir()
    kb = KnowledgeBase.build(tmp_path, encoder=None)
    assert not kb.enabled()
    assert kb.search("anything") == []
    assert kb.best("anything") is None


def test_rrf_merges_bm25_and_semantic_rankings():
    """Two chunks: one wins on exact keywords (BM25), the other only on meaning (semantic).
    RRF should surface both near the top rather than letting either ranking dominate."""
    chunks = [
        Chunk(id="a", source="faq", ref="a", text={"en": "unique keyword zzqux here"}, index_text="unique keyword zzqux here"),
        Chunk(id="b", source="faq", ref="b", text={"en": "a totally different sentence"}, index_text="a totally different sentence"),
    ]
    chunks += [Chunk(id=f"f{i}", source="faq", ref="f", text={"en": f"filler {i}"}, index_text=f"filler {i}") for i in range(4)]
    from rank_bm25 import BM25Okapi

    from satark.harness.knowledge import _tokenise

    bm25 = BM25Okapi([_tokenise(c.index_text) for c in chunks])

    class _FakeEncoder:
        def embed(self, texts):
            # chunk "b" is the semantic match for any query; "a" never is
            return [np.array([0.0, 1.0]) if "b" not in t else np.array([1.0, 0.0]) for t in texts]

    kb = KnowledgeBase(chunks, bm25, _FakeEncoder(), np.array([[0.0, 1.0], [1.0, 0.0]] + [[-1.0, 0.0]] * 4))
    # "b" in the query embeds like chunk b (semantic); "zzqux" is a BM25 hit on a
    hits = kb.search("zzqux b", k=2)
    assert {h.id for h in hits} == {"a", "b"}  # BM25 alone gives only a, semantic alone only b


async def test_search_async_and_best_async_delegate(content_root: Path):
    kb = KnowledgeBase.build(content_root, encoder=None)
    assert await kb.search_async("SEBI registration number", k=1) == kb.search("SEBI registration number", k=1)
    assert (await kb.best_async("SEBI registration number")).id == kb.best("SEBI registration number").id


# ---- real encoder + the shipped content/ (skipped if the model can't load here) --------------

_encoder = load_encoder()


@pytest.mark.skipif(_encoder is None, reason="fastembed model not available in this environment")
def test_real_knowledge_base_cross_lingual_retrieval():
    kb = KnowledgeBase.build(ROOT, _encoder)
    assert kb.enabled() and kb.embeddings is not None
    hit = kb.best("SIP क्या होता है?")
    assert hit is not None
    assert "sip" in hit.rendered("en").lower() or "SIP" in hit.rendered("hi")
