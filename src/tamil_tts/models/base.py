"""Typed TTS model interface (PRD §11).

PRD §11 sketches `synthesize(text, output_path, **opts)`. Here the inputs are bundled into
a typed `SynthesisRequest` (segment id, normalized text, output path, optional reference
audio + transcript) so that every adapter, the cache and the runner share one validated
shape instead of untyped keyword options. `status`, `version_info` and
`supports_reference_audio` are kept as in the PRD.

`BaseTTSModel.synthesize` validates the request, times the call, turns exceptions into
structured errors and verifies that a non-empty output file exists. Adapters implement
only `_synthesize`.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from tamil_tts.config import is_tbd

OUTPUT_SUFFIX = ".wav"  # evaluation audio is WAV (C2 decision 8)


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"  # verified, but not usable here (missing weights/runtime)
    UNVERIFIED = "unverified"  # source/licence/interface not yet verified


class ErrorCode(StrEnum):
    UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_REFERENCE = "unsupported_reference"
    RUNTIME_ERROR = "runtime_error"
    INCOMPLETE_OUTPUT = "incomplete_output"


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    version: str
    source: str | None = None
    license: str | None = None

    def __post_init__(self) -> None:
        if not self.model_id or not self.version:
            raise ValueError("model_id and version are required")


@dataclass(frozen=True)
class ModelStatus:
    identity: ModelIdentity
    availability: Availability
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.availability is not Availability.AVAILABLE and not self.reason:
            raise ValueError("a reason is required when a model is not available")

    @property
    def available(self) -> bool:
        return self.availability is Availability.AVAILABLE


@dataclass(frozen=True)
class ReferenceAudio:
    """Reference prompt for models that condition on audio (e.g. IndicF5)."""

    path: Path
    transcript: str
    checksum: str  # sha256 of the audio file bytes

    @classmethod
    def from_file(cls, path: Path, transcript: str) -> ReferenceAudio:
        return cls(Path(path), transcript, file_sha256(Path(path)))


@dataclass(frozen=True)
class SynthesisRequest:
    segment_id: str
    text: str  # normalized segment text; never the raw source
    output_path: Path
    reference: ReferenceAudio | None = None


@dataclass(frozen=True)
class SynthesisError:
    code: ErrorCode
    message: str


@dataclass(frozen=True)
class RuntimeMetadata:
    wall_time_s: float
    duration_s: float | None = None
    sample_rate: int | None = None
    device: str | None = None
    peak_memory_bytes: int | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthesisResult:
    segment_id: str
    identity: ModelIdentity
    output_path: Path | None
    error: SynthesisError | None = None
    metadata: RuntimeMetadata | None = None
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


@runtime_checkable
class TTSModel(Protocol):
    @property
    def identity(self) -> ModelIdentity: ...

    @property
    def config(self) -> Mapping[str, Any]: ...

    def status(self) -> ModelStatus: ...

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult: ...

    def version_info(self) -> dict[str, Any]: ...

    def supports_reference_audio(self) -> bool: ...


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class BaseTTSModel(ABC):
    """Shared validation, timing and error reporting for adapters."""

    def __init__(self, identity: ModelIdentity, config: Mapping[str, Any] | None = None):
        self._identity = identity
        self._config = MappingProxyType(dict(config or {}))

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

    @property
    def config(self) -> Mapping[str, Any]:
        return self._config

    def version_info(self) -> dict[str, Any]:
        return {
            "model_id": self._identity.model_id,
            "version": self._identity.version,
            "source": self._identity.source,
            "license": self._identity.license,
        }

    @abstractmethod
    def status(self) -> ModelStatus: ...

    @abstractmethod
    def supports_reference_audio(self) -> bool: ...

    @abstractmethod
    def _synthesize(self, request: SynthesisRequest) -> RuntimeMetadata:
        """Write audio to `request.output_path` and return runtime metadata."""

    def _fail(self, request: SynthesisRequest, code: ErrorCode, message: str) -> SynthesisResult:
        return SynthesisResult(
            request.segment_id, self._identity, None, SynthesisError(code, message)
        )

    def _check_request(self, request: SynthesisRequest) -> SynthesisError | None:
        if not request.segment_id:
            return SynthesisError(ErrorCode.INVALID_REQUEST, "segment_id is empty")
        if not request.text.strip():
            return SynthesisError(ErrorCode.INVALID_REQUEST, "text is empty")
        if Path(request.output_path).suffix.lower() != OUTPUT_SUFFIX:
            return SynthesisError(ErrorCode.INVALID_REQUEST, "output_path must be a .wav file")
        if Path(request.output_path).exists():
            # PRD §20: never overwrite experiment outputs.
            return SynthesisError(ErrorCode.INVALID_REQUEST, "output_path already exists")
        reference = request.reference
        if reference is not None:
            if not self.supports_reference_audio():
                return SynthesisError(
                    ErrorCode.UNSUPPORTED_REFERENCE, "model does not accept reference audio"
                )
            if not reference.transcript.strip():
                return SynthesisError(ErrorCode.INVALID_REQUEST, "reference transcript is empty")
            if not Path(reference.path).is_file():
                return SynthesisError(ErrorCode.INVALID_REQUEST, "reference audio not found")
        return None

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        status = self.status()
        if not status.available:
            return self._fail(request, ErrorCode.UNAVAILABLE, status.reason or "unavailable")
        problem = self._check_request(request)
        if problem is not None:
            return self._fail(request, problem.code, problem.message)

        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        try:
            metadata = self._synthesize(request)
        except Exception as exc:  # adapters must not crash the runner
            output.unlink(missing_ok=True)
            return self._fail(request, ErrorCode.RUNTIME_ERROR, f"{type(exc).__name__}: {exc}")
        elapsed = time.perf_counter() - start

        if not output.is_file() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)
            return self._fail(request, ErrorCode.INCOMPLETE_OUTPUT, "no audio was written")
        metadata = RuntimeMetadata(
            wall_time_s=elapsed,
            duration_s=metadata.duration_s,
            sample_rate=metadata.sample_rate,
            device=metadata.device,
            peak_memory_bytes=metadata.peak_memory_bytes,
            extra=metadata.extra,
        )
        return SynthesisResult(request.segment_id, self._identity, output, metadata=metadata)


class UnavailableModel(BaseTTSModel):
    """Placeholder for a candidate that is unverified or cannot run here."""

    def __init__(
        self,
        identity: ModelIdentity,
        reason: str,
        availability: Availability = Availability.UNVERIFIED,
    ):
        if availability is Availability.AVAILABLE:
            raise ValueError("UnavailableModel cannot be available")
        super().__init__(identity)
        self._status = ModelStatus(identity, availability, reason)

    def status(self) -> ModelStatus:
        return self._status

    def supports_reference_audio(self) -> bool:
        return False

    def _synthesize(self, request: SynthesisRequest) -> RuntimeMetadata:
        raise AssertionError("unreachable: status is never available")


def candidate_models(models_config: Mapping[str, Any]) -> dict[str, TTSModel]:
    """Placeholders for every candidate in configs/models.yaml.

    No real adapter exists yet, so every candidate reports UNVERIFIED with the reason.
    """

    def text(value: Any) -> str | None:
        return None if value is None or is_tbd(value) else str(value)

    result: dict[str, TTSModel] = {}
    for name, entry in models_config.get("models", {}).items():
        identity = ModelIdentity(
            model_id=name,
            version=text(entry.get("version")) or "unknown",
            source=text(entry.get("source")),
            license=text(entry.get("license")),
        )
        reason = (
            "no adapter implemented yet"
            if entry.get("verified") is True
            else "source, licence or interface not verified; see docs/MODEL_VERIFICATION.md"
        )
        result[name] = UnavailableModel(identity, reason)
    return result
