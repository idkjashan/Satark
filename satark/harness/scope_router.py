"""Scope router: nearest-neighbour similarity over example utterances, the pattern NVIDIA NeMo
Guardrails' topical rails and aurelio-labs/semantic-router both use for "is this message on
topic". Replaces the chat model's self-label (`_RespondOutput.request` in respond.py): a 3B
model asked to classify its own request refuses real money questions as off-topic and misses
stock-tip requests, because the label and the reply come out of the same small forward pass.
Comparing the user's words to known examples of each route, in a fixed embedding space, is not
hooked to how well the model tells a story about its own reply.

`config/routes.yaml` holds ~15-30 example utterances per route (English, Hindi, Hinglish; never
copied from tests/golden/chat_v1.yaml, or the router would be scored on its own crib sheet).
`ScopeRouter.build()` loads the encoder once; `classify()` (and the off-thread `classify_async()`)
do the embed-and-compare per message. The encoder may fail to load (offline, model not cached):
`enabled()` is False then, and the caller keeps the model's own label.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

log = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _l2_normalise(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.where(norms == 0, 1, norms)


@functools.cache  # one ONNX model per process: each load is ~0.5 GB, and tests build many runtimes
def load_encoder() -> Any | None:
    """A shared `fastembed.TextEmbedding` for the router and the knowledge base (same model,
    one process-wide load). None when fastembed isn't installed or the model can't be fetched
    (offline, no cache) - every caller falls back to a non-semantic path in that case."""
    try:
        from fastembed import TextEmbedding

        # fastembed caches under /tmp by default, which WSL wipes on restart: keep it in the user cache
        cache = os.environ.get("FASTEMBED_CACHE_PATH") or str(Path.home() / ".cache" / "fastembed")
        return TextEmbedding(model_name=MODEL_NAME, cache_dir=cache)
    except Exception as e:  # ImportError, or the ONNX model download/load failing offline
        log.warning("encoder %s unavailable (%s); semantic routing/retrieval is off", MODEL_NAME, type(e).__name__)
        return None


def embed(encoder: Any, texts: list[str]) -> np.ndarray:
    """Normalised embeddings (fastembed's own vectors are not unit-length) so a plain dot
    product is cosine similarity."""
    vecs = np.array(list(encoder.embed(texts)))
    return _l2_normalise(vecs)


@dataclass
class ScopeRouter:
    route_vecs: dict[str, np.ndarray] = field(default_factory=dict)  # route -> (n_utterances, dim), normalised
    encoder: Any | None = None
    threshold: float = 0.3
    margin: float = 0.05

    @classmethod
    def build(cls, config_path: Path, encoder: Any | None, threshold: float = 0.3, margin: float = 0.05) -> ScopeRouter:
        spec = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        routes_cfg = spec.get("routes") or {}
        if encoder is None or not routes_cfg:
            return cls(threshold=threshold, margin=margin)
        route_vecs = {name: embed(encoder, list(utterances)) for name, utterances in routes_cfg.items() if utterances}
        return cls(route_vecs=route_vecs, encoder=encoder, threshold=threshold, margin=margin)

    def enabled(self) -> bool:
        return self.encoder is not None and bool(self.route_vecs)

    def classify(self, text: str) -> str | None:
        """The best-matching route name, or None when the encoder is off, the closest example
        overall is under `threshold`, or the best two ROUTES (each route's own closest example)
        are within `margin` of each other - too close to call, the caller keeps the model's
        self-label in both cases."""
        if not self.enabled() or not (text or "").strip():
            return None
        qv = embed(self.encoder, [text])[0]
        # nearest neighbour per route: the single closest example utterance, not an average -
        # one route having one very on-point example should win over another route's so-so fit.
        scored = sorted(((name, float(np.max(vecs @ qv))) for name, vecs in self.route_vecs.items()), key=lambda kv: -kv[1])
        top_name, top_score = scored[0]
        if top_score < self.threshold:
            return None
        if len(scored) > 1 and (top_score - scored[1][1]) < self.margin:
            return None
        return top_name

    async def classify_async(self, text: str) -> str | None:
        return await asyncio.to_thread(self.classify, text)
