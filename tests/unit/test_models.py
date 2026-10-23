import wave
from pathlib import Path

import pytest

from tamil_tts.config import load_yaml
from tamil_tts.models import (
    Availability,
    ErrorCode,
    ModelIdentity,
    ModelStatus,
    ReferenceAudio,
    SynthesisRequest,
    TTSModel,
    UnavailableModel,
    candidate_models,
)
from tamil_tts.models.mock import MOCK_IDENTITY, MockTTSModel

TEXT = "இன்று காலை மழை பெய்தது."


def _request(tmp_path: Path, name: str = "out.wav", **kwargs) -> SynthesisRequest:
    return SynthesisRequest("TAM-001-S01", TEXT, tmp_path / name, **kwargs)


def _reference(tmp_path: Path, transcript: str = "குறிப்பு வரி.") -> ReferenceAudio:
    path = tmp_path / "ref.wav"
    path.write_bytes(b"not real audio")
    return ReferenceAudio.from_file(path, transcript)


def test_mock_satisfies_protocol():
    assert isinstance(MockTTSModel(), TTSModel)
    assert isinstance(UnavailableModel(MOCK_IDENTITY, "x"), TTSModel)


def test_mock_writes_silent_wav_marked_as_mock(tmp_path):
    result = MockTTSModel().synthesize(_request(tmp_path))
    assert result.ok and result.output_path == tmp_path / "out.wav"
    assert result.identity.model_id == "mock-silence"
    assert result.metadata.extra["mock"] is True
    with wave.open(str(result.output_path)) as wav:
        frames = wav.readframes(wav.getnframes())
        assert wav.getframerate() == result.metadata.sample_rate
    assert frames and set(frames) == {0}  # digital silence, never speech-like
    assert result.metadata.duration_s == pytest.approx(len(TEXT) * 0.01, abs=1e-3)
    assert result.metadata.wall_time_s >= 0


def test_version_info_and_config_are_read_only():
    model = MockTTSModel({"speed": 1.0})
    assert model.version_info()["version"] == "mock-0"
    with pytest.raises(TypeError):
        model.config["speed"] = 2.0  # type: ignore[index]


@pytest.mark.parametrize(
    ("request_kwargs", "code"),
    [
        ({"segment_id": ""}, ErrorCode.INVALID_REQUEST),
        ({"text": "   "}, ErrorCode.INVALID_REQUEST),
        ({"output_path": "out.mp3"}, ErrorCode.INVALID_REQUEST),
    ],
)
def test_invalid_requests(tmp_path, request_kwargs, code):
    fields = {"segment_id": "S", "text": TEXT, "output_path": "out.wav", **request_kwargs}
    fields["output_path"] = tmp_path / fields["output_path"]
    model = MockTTSModel()
    result = model.synthesize(SynthesisRequest(**fields))
    assert not result.ok and result.error.code is code
    assert model.calls == []


def test_existing_output_is_never_overwritten(tmp_path):
    (tmp_path / "out.wav").write_bytes(b"previous result")
    result = MockTTSModel().synthesize(_request(tmp_path))
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert (tmp_path / "out.wav").read_bytes() == b"previous result"


def test_reference_audio(tmp_path):
    reference = _reference(tmp_path)
    assert len(reference.checksum) == 64
    assert MockTTSModel().synthesize(_request(tmp_path, reference=reference)).ok

    unsupported = MockTTSModel(reference_audio=False).synthesize(
        _request(tmp_path, "b.wav", reference=reference)
    )
    assert unsupported.error.code is ErrorCode.UNSUPPORTED_REFERENCE

    empty = _reference(tmp_path, transcript=" ")
    result = MockTTSModel().synthesize(_request(tmp_path, "c.wav", reference=empty))
    assert "transcript" in result.error.message

    missing = ReferenceAudio(tmp_path / "gone.wav", "வரி", "0" * 64)
    result = MockTTSModel().synthesize(_request(tmp_path, "d.wav", reference=missing))
    assert "not found" in result.error.message


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("raise", ErrorCode.RUNTIME_ERROR),
        ("no_output", ErrorCode.INCOMPLETE_OUTPUT),
        ("empty_output", ErrorCode.INCOMPLETE_OUTPUT),
    ],
)
def test_failures_are_reported_not_raised(tmp_path, failure, code):
    result = MockTTSModel(failure=failure).synthesize(_request(tmp_path))
    assert not result.ok and result.error.code is code
    assert result.output_path is None
    assert not (tmp_path / "out.wav").exists()


def test_unavailable_model_reports_reason(tmp_path):
    result = MockTTSModel(available=False).synthesize(_request(tmp_path))
    assert result.error.code is ErrorCode.UNAVAILABLE
    assert "unavailable" in result.error.message

    placeholder = UnavailableModel(MOCK_IDENTITY, "weights not installed", Availability.UNAVAILABLE)
    assert placeholder.status().reason == "weights not installed"
    assert placeholder.synthesize(_request(tmp_path)).error.code is ErrorCode.UNAVAILABLE


def test_status_requires_reason():
    with pytest.raises(ValueError):
        ModelStatus(MOCK_IDENTITY, Availability.UNVERIFIED)
    with pytest.raises(ValueError):
        ModelIdentity("", "1")
    with pytest.raises(ValueError):
        UnavailableModel(MOCK_IDENTITY, "x", Availability.AVAILABLE)
    with pytest.raises(ValueError):
        MockTTSModel(failure="bogus")


def test_candidates_are_all_unverified(config_dir):
    candidates = candidate_models(load_yaml(config_dir / "models.yaml"))
    assert set(candidates) == {"pocket-tts-tamil", "indicf5", "indic-speak"}
    for model in candidates.values():
        status = model.status()
        assert status.availability is Availability.UNVERIFIED
        assert "MODEL_VERIFICATION" in status.reason
