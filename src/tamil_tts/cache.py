"""Local synthesis cache keyed by a stable checksum (PRD §13, §19).

The key covers model identity and version, model configuration, normalized text and,
when used, the reference audio checksum and transcript. Entries live under
$TAMIL_TTS_CACHE_ROOT, never inside the repository:

    <root>/synthesis/<key[:2]>/<key>/audio.wav
    <root>/synthesis/<key[:2]>/<key>/meta.json   # written last; marks the entry complete

An entry without meta.json, or whose audio no longer matches the recorded checksum, is
treated as incomplete: it is removed and counted as a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tamil_tts.config import ConfigError, find_repo_root
from tamil_tts.models.base import (
    ErrorCode,
    ModelIdentity,
    ReferenceAudio,
    SynthesisError,
    SynthesisRequest,
    SynthesisResult,
    TTSModel,
    file_sha256,
)

CACHE_FORMAT_VERSION = 1
AUDIO_NAME = "audio.wav"
META_NAME = "meta.json"


def synthesis_key(
    identity: ModelIdentity,
    config: Mapping[str, Any],
    text: str,
    reference: ReferenceAudio | None = None,
) -> str:
    """Stable sha256 over everything that changes the synthesized audio.

    `config` must be JSON-serializable; key order does not matter.
    """
    payload = {
        "format": CACHE_FORMAT_VERSION,
        "model_id": identity.model_id,
        "model_version": identity.version,
        "config": dict(config),
        "text": text,
        "reference_audio_sha256": reference.checksum if reference else None,
        "reference_transcript": reference.transcript if reference else None,
    }
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except TypeError as exc:
        raise TypeError(f"model config must be JSON-serializable: {exc}") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def request_key(model: TTSModel, request: SynthesisRequest) -> str:
    return synthesis_key(model.identity, model.config, request.text, request.reference)


@dataclass(frozen=True)
class CacheEntry:
    key: str
    audio_path: Path
    meta: dict[str, Any]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    incomplete: int = 0


class SynthesisCache:
    def __init__(self, cache_root: Path, *, repo_root: Path | None = None):
        root = Path(cache_root).expanduser().resolve()
        repo = repo_root or find_repo_root()
        if repo is not None:
            repo = repo.resolve()
            if root == repo or repo in root.parents:
                raise ConfigError(f"cache root {root} is inside the repository; use $HOME")
        self.root = root / "synthesis"
        self.stats = CacheStats()

    def _entry_dir(self, key: str) -> Path:
        if len(key) != 64 or not all(c in "0123456789abcdef" for c in key):
            raise ValueError("cache key must be a sha256 hex digest")
        return self.root / key[:2] / key

    def lookup(self, key: str) -> CacheEntry | None:
        entry_dir = self._entry_dir(key)
        if not entry_dir.exists():
            self.stats.misses += 1
            return None
        audio, meta_path = entry_dir / AUDIO_NAME, entry_dir / META_NAME
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            complete = (
                meta.get("key") == key
                and audio.is_file()
                and audio.stat().st_size == meta.get("audio_bytes")
                and file_sha256(audio) == meta.get("audio_sha256")
            )
        except (OSError, ValueError):
            complete = False
        if not complete:
            self.stats.incomplete += 1
            self.stats.misses += 1
            shutil.rmtree(entry_dir, ignore_errors=True)
            return None
        self.stats.hits += 1
        return CacheEntry(key, audio, meta)

    def store(self, key: str, audio_source: Path, meta: Mapping[str, Any]) -> CacheEntry:
        source = Path(audio_source)
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError(f"refusing to cache missing or empty audio: {source}")
        entry_dir = self._entry_dir(key)
        shutil.rmtree(entry_dir, ignore_errors=True)
        entry_dir.mkdir(parents=True)
        audio = entry_dir / AUDIO_NAME
        _atomic_copy(source, audio)
        record = {
            **meta,
            "key": key,
            "format": CACHE_FORMAT_VERSION,
            "audio_bytes": audio.stat().st_size,
            "audio_sha256": file_sha256(audio),
        }
        _atomic_write(entry_dir / META_NAME, json.dumps(record, ensure_ascii=False, indent=2))
        return CacheEntry(key, audio, record)

    def invalidate(self, key: str) -> bool:
        entry_dir = self._entry_dir(key)
        if not entry_dir.exists():
            return False
        shutil.rmtree(entry_dir)
        return True

    def synthesize(self, model: TTSModel, request: SynthesisRequest) -> SynthesisResult:
        """Return cached audio when the key matches; otherwise synthesize and cache it."""
        key = request_key(model, request)
        output = Path(request.output_path)
        if output.exists():
            # Same rule as BaseTTSModel: never overwrite experiment outputs.
            return SynthesisResult(
                request.segment_id,
                model.identity,
                None,
                SynthesisError(ErrorCode.INVALID_REQUEST, "output_path already exists"),
            )
        entry = self.lookup(key)
        if entry is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            _atomic_copy(entry.audio_path, output)
            return SynthesisResult(request.segment_id, model.identity, output, cached=True)

        result = model.synthesize(request)
        if result.ok and result.output_path is not None:
            meta = {
                "model": model.version_info(),
                "segment_id": request.segment_id,
                "duration_s": result.metadata.duration_s if result.metadata else None,
                "sample_rate": result.metadata.sample_rate if result.metadata else None,
            }
            self.store(key, result.output_path, meta)
        return replace(result, cached=False)


def _atomic_copy(source: Path, target: Path) -> None:
    tmp = target.with_name(target.name + ".partial")
    shutil.copyfile(source, tmp)
    os.replace(tmp, target)


def _atomic_write(target: Path, text: str) -> None:
    tmp = target.with_name(target.name + ".partial")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
