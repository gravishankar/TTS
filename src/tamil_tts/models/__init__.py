"""Common TTS model interface (PRD §11). Real adapters are added only after verification."""

from tamil_tts.models.base import (
    Availability,
    BaseTTSModel,
    ErrorCode,
    ModelIdentity,
    ModelStatus,
    ReferenceAudio,
    RuntimeMetadata,
    SynthesisError,
    SynthesisRequest,
    SynthesisResult,
    TTSModel,
    UnavailableModel,
    candidate_models,
)

__all__ = [
    "Availability",
    "BaseTTSModel",
    "ErrorCode",
    "ModelIdentity",
    "ModelStatus",
    "ReferenceAudio",
    "RuntimeMetadata",
    "SynthesisError",
    "SynthesisRequest",
    "SynthesisResult",
    "TTSModel",
    "UnavailableModel",
    "candidate_models",
]
