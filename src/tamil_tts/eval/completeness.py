"""Audio completeness checks for synthesized segments (PRD §13, §16).

Only deterministic checks are made here: the file exists, is a readable WAV with audio
data, and is not digital silence (every sample exactly zero). Duration and near-silence
thresholds are TBD in configs/eval.yaml and are not guessed.

WAV headers are parsed directly (not with the `wave` module) so that 32-bit float WAV,
which some candidate models write, is accepted too.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PCM, IEEE_FLOAT, EXTENSIBLE = 1, 3, 0xFFFE
_BLOCK = 1 << 16


class AudioCheckError(Exception):
    """The file is not a usable WAV."""


class SegmentAudioStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    INVALID = "invalid"
    EMPTY = "empty"
    SILENT = "silent"


@dataclass(frozen=True)
class AudioInfo:
    format_tag: int
    channels: int
    sample_rate: int
    bits_per_sample: int
    data_bytes: int
    duration_s: float
    digital_silence: bool


@dataclass(frozen=True)
class SegmentCheck:
    status: SegmentAudioStatus
    message: str = ""
    duration_s: float | None = None
    sample_rate: int | None = None

    @property
    def ok(self) -> bool:
        return self.status is SegmentAudioStatus.OK


def inspect_wav(path: Path) -> AudioInfo:
    with Path(path).open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise AudioCheckError("not a RIFF/WAVE file")
        fmt: tuple[int, int, int, int, int] | None = None
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                raise AudioCheckError("no data chunk")
            chunk_id, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if chunk_id == b"fmt ":
                body = handle.read(size)
                if len(body) < 16:
                    raise AudioCheckError("fmt chunk too short")
                tag, channels, rate, _, block_align, bits = struct.unpack("<HHIIHH", body[:16])
                if tag == EXTENSIBLE and len(body) >= 26:
                    tag = struct.unpack("<H", body[24:26])[0]
                fmt = (tag, channels, rate, block_align, bits)
                if size % 2:
                    handle.read(1)
            elif chunk_id == b"data":
                if fmt is None:
                    raise AudioCheckError("data chunk before fmt chunk")
                return _read_data(handle, size, fmt)
            else:
                handle.seek(size + (size % 2), 1)


def _read_data(handle, declared: int, fmt: tuple[int, int, int, int, int]) -> AudioInfo:
    tag, channels, rate, block_align, bits = fmt
    if tag not in (PCM, IEEE_FLOAT):
        raise AudioCheckError(f"unsupported WAV format tag {tag}")
    if channels < 1 or rate < 1 or block_align < 1:
        raise AudioCheckError("invalid fmt values")
    silent_byte = 0x80 if (tag == PCM and bits == 8) else 0x00
    total, silent = 0, True
    remaining = declared  # streaming writers may declare 0xFFFFFFFF; stop at EOF
    while remaining > 0:
        block = handle.read(min(_BLOCK, remaining))
        if not block:
            break
        total += len(block)
        remaining -= len(block)
        if silent and block.count(silent_byte) != len(block):
            silent = False
    frames = total // block_align
    return AudioInfo(tag, channels, rate, bits, total, frames / rate, silent and total > 0)


def check_segment_audio(path: Path | None) -> SegmentCheck:
    if path is None or not Path(path).is_file():
        return SegmentCheck(SegmentAudioStatus.MISSING, "no audio file")
    try:
        info = inspect_wav(Path(path))
    except (AudioCheckError, OSError, struct.error) as exc:
        return SegmentCheck(SegmentAudioStatus.INVALID, str(exc))
    if info.data_bytes == 0 or info.duration_s == 0:
        return SegmentCheck(SegmentAudioStatus.EMPTY, "no audio samples", 0.0, info.sample_rate)
    if info.digital_silence:
        return SegmentCheck(
            SegmentAudioStatus.SILENT, "digital silence", info.duration_s, info.sample_rate
        )
    return SegmentCheck(SegmentAudioStatus.OK, "", info.duration_s, info.sample_rate)
