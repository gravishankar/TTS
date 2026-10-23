"""Mock TTS model for automated tests.

It writes digital silence, never speech-like sound, so its output cannot be mistaken
for a real model: silence checks flag it and listeners hear nothing. Its identity says
"mock" and every result carries `extra["mock"] = True`.
"""

from __future__ import annotations

import wave
from collections.abc import Mapping
from typing import Any

from tamil_tts.models.base import (
    Availability,
    BaseTTSModel,
    ModelIdentity,
    ModelStatus,
    RuntimeMetadata,
    SynthesisRequest,
)

MOCK_IDENTITY = ModelIdentity(model_id="mock-silence", version="mock-0", license="test-only")
SAMPLE_RATE = 16_000
SECONDS_PER_CHAR = 0.01


class MockTTSModel(BaseTTSModel):
    """Configurable failure modes: "raise", "no_output", "empty_output"."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        identity: ModelIdentity = MOCK_IDENTITY,
        reference_audio: bool = True,
        available: bool = True,
        failure: str | None = None,
    ):
        if failure not in (None, "raise", "no_output", "empty_output"):
            raise ValueError(f"unknown failure mode: {failure}")
        super().__init__(identity, config)
        self._reference_audio = reference_audio
        self._available = available
        self._failure = failure
        self.calls: list[SynthesisRequest] = []

    def status(self) -> ModelStatus:
        if self._available:
            return ModelStatus(self.identity, Availability.AVAILABLE)
        return ModelStatus(self.identity, Availability.UNAVAILABLE, "mock configured unavailable")

    def supports_reference_audio(self) -> bool:
        return self._reference_audio

    def _synthesize(self, request: SynthesisRequest) -> RuntimeMetadata:
        self.calls.append(request)
        if self._failure == "raise":
            raise RuntimeError("mock failure")
        if self._failure == "no_output":
            return RuntimeMetadata(wall_time_s=0.0)
        if self._failure == "empty_output":
            request.output_path.write_bytes(b"")
            return RuntimeMetadata(wall_time_s=0.0)

        frames = max(1, int(len(request.text) * SECONDS_PER_CHAR * SAMPLE_RATE))
        with wave.open(str(request.output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(b"\x00\x00" * frames)
        return RuntimeMetadata(
            wall_time_s=0.0,
            duration_s=frames / SAMPLE_RATE,
            sample_rate=SAMPLE_RATE,
            device="none",
            extra={"mock": True},
        )
