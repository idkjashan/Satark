"""Knowledge retrieval with citations (RAG - retrieval-augmented generation) over Satark's own
content: content/faq.json, content/lessons/*.json, content/sims/*.json. One chunk per FAQ
answer, lesson step or sim summary (CONTRACTS Track C note). Hybrid search: BM25 (lexical,
`rank_bm25`) plus the same fastembed encoder the scope router uses (semantic, cross-lingual),
merged by reciprocal rank fusion (RRF) so neither ranking has to be rescaled to match the other.

respond.py puts the top few chunks into the answer prompt as numbered knowledge ("[K1] ...");
the model's `cites` then names K-ids, which respond.py maps back to real chunk ids (`faq:...`,
`lesson:...:<step>`, `sim:...`) for the PWA's "Learn more" links. Nothing here calls an LLM;
`search()`/`best()` call the embedding encoder, which is synchronous CPU work, so callers use
`search_async()`/`best_async()` (off the event loop thread) from async code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[\wऀ-ॿ]+")
_RRF_K = 60  # standard RRF damping constant: rank 1 contributes 1/61, rank 2 1/62, ...


def _tokenise(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Chunk:
    id: str  # "faq:<intent id>", "lesson:<lesson id>:<step no>", "sim:<sim id>"
    source: str  # "faq" | "lesson" | "sim"
    ref: str  # the lesson/sim id alone, for the PWA's "Learn more: <ref>" link
    text: dict[str, str]  # lang -> text, "en" always present
    index_text: str  # en + hi concatenated: what BM25 tokenises and the encoder embeds

    def rendered(self, lang: str) -> str:
        return self.text.get(lang) or self.text.get("en") or ""


def _faq_chunks(faq: dict[str, Any]) -> list[Chunk]:
    out = []
    for intent in faq.get("intents", []) or []:
        answer = intent.get("answer") or {}
        en, hi = (answer.get("en") or "").strip(), (answer.get("hi") or "").strip()
        if not en and not hi:
            continue
        out.append(Chunk(id=f"faq:{intent['id']}", source="faq", ref=intent["id"],
                          text={"en": en, "hi": hi}, index_text=f"{en} {hi}".strip()))
    return out


def _lesson_chunks(lessons_dir: Path) -> list[Chunk]:
    out = []
    for p in sorted(lessons_dir.glob("*.json")) if lessons_dir.exists() else []:
        data = json.loads(p.read_text(encoding="utf-8"))
        lid = data.get("id", p.stem)
        for i, step in enumerate(data.get("steps", []) or [], 1):
            t = step.get("text") or {}
            en, hi = (t.get("en") or "").strip(), (t.get("hi") or "").strip()
            if not en and not hi:
                continue
            out.append(Chunk(id=f"lesson:{lid}:{i}", source="lesson", ref=lid,
                              text={"en": en, "hi": hi}, index_text=f"{en} {hi}".strip()))
    return out


def _sim_chunks(sims_dir: Path) -> list[Chunk]:
    """One chunk per sim: the title plus every state's narration, standing in for "what this
    simulation teaches" without needing the player's actual path through it."""
    out = []
    for p in sorted(sims_dir.glob("*.json")) if sims_dir.exists() else []:
        data = json.loads(p.read_text(encoding="utf-8"))
        sid = data.get("id", p.stem)
        title = data.get("title") or {}
        states = (data.get("states") or {}).values()

        def bits(lang: str) -> str:
            parts = [title.get(lang, "")]
            for s in states:
                parts.append((s.get("say") or {}).get(lang, ""))
                parts.append((s.get("reveal") or {}).get(lang, ""))
            return " ".join(p.strip() for p in parts if p and p.strip())

        en, hi = bits("en")[:700], bits("hi")[:700]
        if not en and not hi:
            continue
        out.append(Chunk(id=f"sim:{sid}", source="sim", ref=sid, text={"en": en, "hi": hi},
                          index_text=f"{en} {hi}".strip()))
    return out


class KnowledgeBase:
    def __init__(self, chunks: list[Chunk], bm25: Any | None, encoder: Any | None, embeddings: np.ndarray | None) -> None:
        self.chunks = chunks
        self.bm25 = bm25
        self.encoder = encoder
        self.embeddings = embeddings  # (n_chunks, dim), normalised; None when the encoder is off

    @classmethod
    def build(cls, root: Path, encoder: Any | None) -> KnowledgeBase:
        content = root / "content"
        faq_path = content / "faq.json"
        faq = json.loads(faq_path.read_text(encoding="utf-8")) if faq_path.exists() else {}
        chunks = _faq_chunks(faq) + _lesson_chunks(content / "lessons") + _sim_chunks(content / "sims")

        bm25 = None
        if chunks:
            try:
                from rank_bm25 import BM25Okapi

                bm25 = BM25Okapi([_tokenise(c.index_text) for c in chunks])
            except ImportError:
                log.warning("rank_bm25 not installed; retrieval runs on the semantic half only")

        embeddings = None
        if chunks and encoder is not None:
            from satark.harness.scope_router import embed

            embeddings = embed(encoder, [c.index_text for c in chunks])
        return cls(chunks, bm25, encoder if embeddings is not None else None, embeddings)

    def enabled(self) -> bool:
        return bool(self.chunks)

    def _ranking(self, scores: np.ndarray, k: int) -> list[int]:
        order = np.argsort(scores)[::-1]
        return [int(i) for i in order[: max(k * 4, 10)] if scores[i] > 0]

    def _rrf(self, query: str, k: int) -> list[Chunk]:
        """Reciprocal rank fusion: each chunk's fused score is the sum of 1/(RRF_K + rank) over
        the ranked lists it appears in. RRF merges rankings on different scales (BM25's raw
        scores, cosine similarity in [-1, 1]) without needing a weight between them."""
        fused: dict[int, float] = {}
        if self.bm25 is not None:
            for rank, idx in enumerate(self._ranking(np.asarray(self.bm25.get_scores(_tokenise(query))), k)):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (_RRF_K + rank)
        if self.encoder is not None and self.embeddings is not None:
            from satark.harness.scope_router import embed

            qv = embed(self.encoder, [query])[0]
            for rank, idx in enumerate(self._ranking(self.embeddings @ qv, k)):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (_RRF_K + rank)
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [self.chunks[idx] for idx, _ in ranked]

    def search(self, query: str, k: int = 4) -> list[Chunk]:
        if not self.enabled() or not (query or "").strip():
            return []
        return self._rrf(query, k)

    def best(self, query: str) -> Chunk | None:
        hits = self.search(query, k=1)
        return hits[0] if hits else None

    async def search_async(self, query: str, k: int = 4) -> list[Chunk]:
        return await asyncio.to_thread(self.search, query, k)

    async def best_async(self, query: str) -> Chunk | None:
        return await asyncio.to_thread(self.best, query)
