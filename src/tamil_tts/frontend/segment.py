"""Sentence segmentation with source offsets and completeness checks (PRD §10).

Segmentation runs on the source text so offsets always point into the original;
each segment is then normalized on its own. Every non-whitespace source character
must end up in exactly one segment, otherwise `SegmentationError` is raised.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from tamil_tts.frontend.normalize import Normalizer

SENTENCE_TERMINATORS = frozenset(".?!…")
CLAUSE_BREAKS = frozenset(",;:")
CLOSERS = frozenset("\"'”’)]}»")


class SegmentationError(Exception):
    """Segmentation lost, duplicated or reordered source text."""


@dataclass(frozen=True)
class Segment:
    segment_id: str
    utterance_id: str
    index: int
    source_start: int
    source_end: int
    source_text: str
    segment_text: str
    checksum: str
    expected_length: int


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _boundary_spans(
    text: str, breaks: frozenset[str], start: int, end: int
) -> list[tuple[int, int]]:
    """Split text[start:end] after break characters that are followed by whitespace or end."""
    spans: list[tuple[int, int]] = []
    span_start = i = start
    while i < end:
        if text[i] in breaks:
            j = i + 1
            while j < end and (text[j] in breaks or text[j] in CLOSERS):
                j += 1
            if j == end or text[j].isspace():
                spans.append((span_start, j))
                span_start = i = j
                continue
        i += 1
    spans.append((span_start, end))
    trimmed = (_trim(text, s, e) for s, e in spans)
    return [(s, e) for s, e in trimmed if s < e]


def _split_long(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Greedily merge clauses up to `max_chars`; never split inside a clause."""
    clauses = _boundary_spans(text, CLAUSE_BREAKS, start, end)
    pieces: list[tuple[int, int]] = []
    for s, e in clauses:
        if pieces and e - pieces[-1][0] <= max_chars:
            pieces[-1] = (pieces[-1][0], e)
        else:
            pieces.append((s, e))
    return pieces


def segment_text(
    utterance_id: str,
    source_text: str,
    *,
    normalizer: Normalizer | None = None,
    max_chars: int | None = None,
) -> list[Segment]:
    """Segment `source_text` into sentences, splitting long ones only at clause punctuation.

    `max_chars` is TBD in the PRD; with None, sentences are never split further.
    """
    if max_chars is not None and max_chars < 1:
        raise ValueError("max_chars must be positive")
    normalizer = normalizer or Normalizer()

    spans: list[tuple[int, int]] = []
    for s, e in _boundary_spans(source_text, SENTENCE_TERMINATORS, 0, len(source_text)):
        if max_chars is not None and e - s > max_chars:
            spans.extend(_split_long(source_text, s, e, max_chars))
        else:
            spans.append((s, e))

    segments: list[Segment] = []
    for s, e in spans:
        normalized = normalizer.normalize(source_text[s:e]).normalized_text
        if not normalized:
            raise SegmentationError(f"{utterance_id}: text at {s}:{e} normalized to nothing")
        index = len(segments) + 1
        segments.append(
            Segment(
                segment_id=f"{utterance_id}-S{index:02d}",
                utterance_id=utterance_id,
                index=index,
                source_start=s,
                source_end=e,
                source_text=source_text[s:e],
                segment_text=normalized,
                checksum=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                expected_length=len(normalized),
            )
        )
    verify_coverage(source_text, segments)
    return segments


def verify_coverage(source_text: str, segments: list[Segment]) -> None:
    """Raise unless segments cover all non-whitespace source text in order, without overlap."""
    position = 0
    for seg in segments:
        if seg.source_start < position:
            raise SegmentationError(f"{seg.segment_id} overlaps or is out of order")
        gap = source_text[position : seg.source_start]
        if gap.strip():
            raise SegmentationError(f"text lost before {seg.segment_id}: {gap.strip()!r}")
        if source_text[seg.source_start : seg.source_end] != seg.source_text:
            raise SegmentationError(f"{seg.segment_id} does not match its source offsets")
        position = seg.source_end
    tail = source_text[position:]
    if tail.strip():
        raise SegmentationError(f"text lost at end: {tail.strip()!r}")
