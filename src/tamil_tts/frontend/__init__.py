"""Tamil speech front end: normalization and segmentation (PRD §10)."""

from tamil_tts.frontend.normalize import NormalizedText, Normalizer
from tamil_tts.frontend.segment import Segment, SegmentationError, segment_text

__all__ = ["NormalizedText", "Normalizer", "Segment", "SegmentationError", "segment_text"]
