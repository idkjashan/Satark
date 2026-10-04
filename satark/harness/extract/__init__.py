"""Entity extraction: normalisation, regex/QR/LLM/OCR extraction, masking glue (CONTRACTS §4).

Everyone else imports from here, not from the submodules directly.
"""

from __future__ import annotations

from satark.harness.extract.llm import Extraction
from satark.harness.extract.normalise import fold_pattern, normalise_text
from satark.harness.extract.pipeline import ExtractorPipeline

__all__ = ["ExtractorPipeline", "Extraction", "fold_pattern", "normalise_text"]
