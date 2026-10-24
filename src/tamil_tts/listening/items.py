"""Listening items built from an experiment run directory.

Each segment row in `segments.jsonl` becomes an item. Its audio is re-checked when the
session loads and classified as:

- real     model audio that passed the automatic checks; the only kind that can be rated
- mock     produced by a mock model (never presented as speech)
- missing  no audio file
- invalid  unreadable or empty WAV
- silent   digital silence
- error    synthesis failed

Mock items never enter a session: `for_session` refuses a mock run and drops mock items
from a mixed run, reporting only their count.

Text is attached from the private manifest, and only when the re-segmented text matches
the run's segment checksum. In blind mode it is revealed only after an item is rated.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from tamil_tts.eval.completeness import SegmentAudioStatus, check_segment_audio
from tamil_tts.frontend import segment_text
from tamil_tts.manifest import load_manifest
from tamil_tts.models.base import file_sha256


class AudioKind(StrEnum):
    REAL = "real"
    MOCK = "mock"
    MISSING = "missing"
    INVALID = "invalid"
    SILENT = "silent"
    ERROR = "error"


AUDIO_KIND_TEXT = {
    AudioKind.REAL: "Real model audio",
    AudioKind.MOCK: "Mock audio (silent test output, not speech) — cannot be rated",
    AudioKind.MISSING: "Audio missing — cannot be rated",
    AudioKind.INVALID: "Audio invalid or empty — cannot be rated",
    AudioKind.SILENT: "Audio is silent — cannot be rated",
    AudioKind.ERROR: "Synthesis failed — cannot be rated",
}


class RunLoadError(Exception):
    """The run directory is not a complete experiment run, or cannot be evaluated."""


@dataclass(frozen=True)
class ListeningItem:
    key: str  # "<system_id>/<segment_id>"
    system_id: str
    segment_id: str
    entry_id: str
    split: str
    tags: tuple[str, ...]
    segment_sha256: str
    audio_kind: AudioKind
    audio_path: Path | None
    audio_sha256: str | None
    duration_s: float | None
    model_id: str = ""
    model_version: str = ""
    text: str | None = None  # only in text mode; never written to exported files
    text_note: str | None = None

    @property
    def rateable(self) -> bool:
        return self.audio_kind is AudioKind.REAL


def _classify(
    row: dict[str, Any], run_dir: Path, mock_system: bool
) -> tuple[AudioKind, Path | None]:
    if row.get("status") == "error":
        return AudioKind.ERROR, None
    rel = row.get("audio")
    path = (run_dir / rel).resolve() if rel else None
    if path is not None and run_dir.resolve() not in path.parents:
        return AudioKind.INVALID, None  # refuse paths outside the run directory
    if mock_system:
        return AudioKind.MOCK, path if path and path.is_file() else None
    check = check_segment_audio(path)
    if check.status is SegmentAudioStatus.OK:
        return AudioKind.REAL, path
    if check.status is SegmentAudioStatus.MISSING:
        return AudioKind.MISSING, None
    if check.status is SegmentAudioStatus.SILENT:
        return AudioKind.SILENT, path
    return AudioKind.INVALID, None


def load_run(run_dir: Path) -> tuple[dict[str, Any], list[ListeningItem]]:
    """Load results.json and segments.jsonl and classify every segment's audio."""
    run_dir = Path(run_dir)
    results_path, segments_path = run_dir / "results.json", run_dir / "segments.jsonl"
    if not results_path.is_file() or not segments_path.is_file():
        raise RunLoadError(f"not a complete run (results.json/segments.jsonl missing): {run_dir}")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    models = {s["system_id"]: s.get("model", {}) for s in results.get("systems", [])}
    mock_systems = {
        s["system_id"]
        for s in results.get("systems", [])
        if results.get("mock") or str(s.get("model", {}).get("model_id", "")).startswith("mock")
    }
    items: list[ListeningItem] = []
    for line in segments_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        kind, path = _classify(row, run_dir, row["system_id"] in mock_systems)
        items.append(
            ListeningItem(
                key=f"{row['system_id']}/{row['segment_id']}",
                system_id=row["system_id"],
                segment_id=row["segment_id"],
                entry_id=row["id"],
                split=row["split"],
                tags=tuple(row.get("tags", [])),
                segment_sha256=row["segment_sha256"],
                audio_kind=kind,
                audio_path=path,
                audio_sha256=file_sha256(path) if kind is AudioKind.REAL and path else None,
                duration_s=row.get("duration_s"),
                model_id=str(models.get(row["system_id"], {}).get("model_id", "")),
                model_version=str(models.get(row["system_id"], {}).get("version", "")),
            )
        )
    return results, items


def attach_text(
    items: list[ListeningItem], manifest_path: Path, max_chars: int | None
) -> list[ListeningItem]:
    """Attach reference text from the private manifest, verified by segment checksum."""
    report = load_manifest(manifest_path)
    if not report.ok:
        raise RunLoadError("manifest is invalid; run `tamil-tts manifest validate`")
    entries = {e.id: e for e in report.entries}
    segments: dict[str, tuple[str, str]] = {}
    for entry_id in {i.entry_id for i in items}:
        entry = entries.get(entry_id)
        if entry is None:
            continue
        for seg in segment_text(entry.id, entry.text, max_chars=max_chars):
            segments[seg.segment_id] = (seg.segment_text, seg.checksum)
    attached = []
    for item in items:
        found = segments.get(item.segment_id)
        if found is None:
            attached.append(replace(item, text_note="text not found in manifest"))
        elif found[1] != item.segment_sha256:
            attached.append(replace(item, text_note="text does not match this audio segment"))
        else:
            attached.append(replace(item, text=found[0]))
    return attached


def for_session(
    results: dict[str, Any], items: list[ListeningItem]
) -> tuple[list[ListeningItem], int]:
    """Items allowed into an evaluation session, and the number of mock items dropped."""
    if results.get("mock"):
        raise RunLoadError("this is a mock run; mock audio cannot enter an evaluation session")
    kept = [i for i in items if i.audio_kind is not AudioKind.MOCK]
    if not kept:
        raise RunLoadError("no non-mock items in this run; nothing can be evaluated")
    return kept, len(items) - len(kept)


def ordered(items: list[ListeningItem], seed: str) -> list[ListeningItem]:
    """Shuffle items (and so model presentation order) with a recorded seed (PRD §17)."""
    shuffled = sorted(items, key=lambda i: i.key)
    random.Random(seed).shuffle(shuffled)
    return shuffled
