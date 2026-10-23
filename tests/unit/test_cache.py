import json
from pathlib import Path

import pytest

from tamil_tts.cache import SynthesisCache, request_key, synthesis_key
from tamil_tts.config import ConfigError
from tamil_tts.models import ErrorCode, ModelIdentity, ReferenceAudio, SynthesisRequest
from tamil_tts.models.mock import MOCK_IDENTITY, MockTTSModel

TEXT = "அம்மா சுவையான உணவு சமைத்தார்."


@pytest.fixture
def cache(tmp_path) -> SynthesisCache:
    return SynthesisCache(tmp_path / "cache", repo_root=tmp_path / "repo")


def _request(tmp_path: Path, name: str, text: str = TEXT, **kwargs) -> SynthesisRequest:
    return SynthesisRequest("TAM-007-S01", text, tmp_path / "out" / name, **kwargs)


def _reference(tmp_path: Path, data: bytes = b"ref", transcript: str = "வரி") -> ReferenceAudio:
    path = tmp_path / f"ref-{len(data)}.wav"
    path.write_bytes(data)
    return ReferenceAudio.from_file(path, transcript)


# --- key -------------------------------------------------------------------


def test_key_is_stable_and_order_independent():
    a = synthesis_key(MOCK_IDENTITY, {"x": 1, "y": [1, 2]}, TEXT)
    b = synthesis_key(MOCK_IDENTITY, {"y": [1, 2], "x": 1}, TEXT)
    assert a == b and len(a) == 64


def test_key_changes_with_every_component(tmp_path):
    base = synthesis_key(MOCK_IDENTITY, {"x": 1}, TEXT)
    ref = _reference(tmp_path)
    variants = [
        synthesis_key(ModelIdentity("other", "mock-0"), {"x": 1}, TEXT),
        synthesis_key(ModelIdentity("mock-silence", "mock-1"), {"x": 1}, TEXT),
        synthesis_key(MOCK_IDENTITY, {"x": 2}, TEXT),
        synthesis_key(MOCK_IDENTITY, {"x": 1}, TEXT + " "),
        synthesis_key(MOCK_IDENTITY, {"x": 1}, TEXT, ref),
        synthesis_key(MOCK_IDENTITY, {"x": 1}, TEXT, _reference(tmp_path, b"other")),
        synthesis_key(MOCK_IDENTITY, {"x": 1}, TEXT, _reference(tmp_path, transcript="வேறு")),
    ]
    assert len({base, *variants}) == len(variants) + 1


def test_segment_id_and_output_path_do_not_change_key(tmp_path):
    model = MockTTSModel()
    a = request_key(model, _request(tmp_path, "a.wav"))
    b = request_key(model, SynthesisRequest("OTHER-S09", TEXT, tmp_path / "b.wav"))
    assert a == b


def test_non_json_config_rejected():
    with pytest.raises(TypeError, match="JSON-serializable"):
        synthesis_key(MOCK_IDENTITY, {"path": Path("/x")}, TEXT)


# --- cache behaviour -------------------------------------------------------


def test_miss_then_hit(tmp_path, cache):
    model = MockTTSModel()
    first = cache.synthesize(model, _request(tmp_path, "a.wav"))
    assert first.ok and not first.cached and len(model.calls) == 1

    second = cache.synthesize(model, _request(tmp_path, "b.wav"))
    assert second.ok and second.cached and len(model.calls) == 1
    assert second.output_path.read_bytes() == first.output_path.read_bytes()
    assert (cache.stats.hits, cache.stats.misses) == (1, 1)


def test_changed_text_or_config_misses(tmp_path, cache):
    cache.synthesize(MockTTSModel(), _request(tmp_path, "a.wav"))
    other_text = cache.synthesize(MockTTSModel(), _request(tmp_path, "b.wav", text="வேறு வரி."))
    other_config = cache.synthesize(MockTTSModel({"speed": 0.9}), _request(tmp_path, "c.wav"))
    assert not other_text.cached and not other_config.cached


def test_reference_audio_change_misses(tmp_path, cache):
    model = MockTTSModel()
    cache.synthesize(model, _request(tmp_path, "a.wav", reference=_reference(tmp_path)))
    changed = _reference(tmp_path, b"different bytes")
    assert not cache.synthesize(model, _request(tmp_path, "b.wav", reference=changed)).cached


def test_invalidate(tmp_path, cache):
    model = MockTTSModel()
    request = _request(tmp_path, "a.wav")
    cache.synthesize(model, request)
    key = request_key(model, request)
    assert cache.invalidate(key) is True
    assert cache.invalidate(key) is False
    assert not cache.synthesize(model, _request(tmp_path, "b.wav")).cached
    assert len(model.calls) == 2


def _stored_entry(tmp_path, cache):
    model = MockTTSModel()
    request = _request(tmp_path, "a.wav")
    cache.synthesize(model, request)
    return model, cache.root / request_key(model, request)[:2] / request_key(model, request)


def test_missing_meta_is_incomplete(tmp_path, cache):
    model, entry = _stored_entry(tmp_path, cache)
    (entry / "meta.json").unlink()
    result = cache.synthesize(model, _request(tmp_path, "b.wav"))
    assert not result.cached and cache.stats.incomplete == 1
    assert (entry / "meta.json").is_file()  # re-synthesized and stored again


def test_corrupted_audio_is_incomplete(tmp_path, cache):
    model, entry = _stored_entry(tmp_path, cache)
    (entry / "audio.wav").write_bytes(b"truncated")
    assert not cache.synthesize(model, _request(tmp_path, "b.wav")).cached
    assert cache.stats.incomplete == 1


def test_garbled_meta_is_incomplete(tmp_path, cache):
    model, entry = _stored_entry(tmp_path, cache)
    (entry / "meta.json").write_text("{not json")
    assert not cache.synthesize(model, _request(tmp_path, "b.wav")).cached


def test_failed_synthesis_is_not_cached(tmp_path, cache):
    request = _request(tmp_path, "a.wav")
    result = cache.synthesize(MockTTSModel(failure="empty_output"), request)
    assert result.error.code is ErrorCode.INCOMPLETE_OUTPUT
    assert cache.lookup(request_key(MockTTSModel(), request)) is None
    assert not cache.root.exists() or not any(cache.root.rglob("audio.wav"))


def test_store_refuses_empty_audio(tmp_path, cache):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        cache.store("a" * 64, empty, {})


def test_meta_records_checksum(tmp_path, cache):
    _, entry = _stored_entry(tmp_path, cache)
    meta = json.loads((entry / "meta.json").read_text())
    assert len(meta["audio_sha256"]) == 64
    assert meta["model"]["model_id"] == "mock-silence"


def test_existing_output_not_overwritten_on_hit(tmp_path, cache):
    model = MockTTSModel()
    cache.synthesize(model, _request(tmp_path, "a.wav"))
    target = tmp_path / "out" / "b.wav"
    target.write_bytes(b"keep me")
    result = cache.synthesize(model, _request(tmp_path, "b.wav"))
    assert result.error.code is ErrorCode.INVALID_REQUEST
    assert target.read_bytes() == b"keep me"


def test_cache_root_inside_repo_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ConfigError, match="inside the repository"):
        SynthesisCache(repo / ".cache", repo_root=repo)


def test_bad_key_rejected(cache):
    with pytest.raises(ValueError):
        cache.lookup("../../etc")
