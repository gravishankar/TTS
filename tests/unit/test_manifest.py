import json

from tamil_tts.manifest import load_manifest, validate_record

GOOD = {
    "id": "TAM-001",
    "split": "train",
    "text": "இன்று காலை மழை பெய்தது.",
    "audio": "${TAM_AUDIO_ROOT}/TAM-001.wav",
    "speaker_id": "SPK-01",
    "tags": ["literary", "PHON-LIQUID"],
    "quality": "accepted",
}


def _errors(record):
    _, issues = validate_record(record)
    return [i.message for i in issues if i.severity == "error"]


def test_prd_example_record_is_valid():
    entry, issues = validate_record(GOOD)
    assert entry is not None and entry.tags == ("literary", "PHON-LIQUID")
    assert issues == []


def test_valid_fixture(fixtures):
    report = load_manifest(fixtures / "manifests" / "valid.jsonl")
    assert report.ok, [str(i) for i in report.issues]
    assert len(report.entries) == 10
    assert report.warnings == []


def test_invalid_fixture(fixtures):
    report = load_manifest(fixtures / "manifests" / "invalid.jsonl")
    messages = [str(i) for i in report.errors]
    assert len(report.entries) == 1
    assert any("split must be one of" in m for m in messages)
    assert any("no personal or absolute paths" in m for m in messages)
    assert any("pseudonymous" in m for m in messages)
    assert any(".wav" in m for m in messages)
    assert any("invalid JSON" in m and "line 4" in m for m in messages)


def test_duplicate_ids_rejected():
    from tamil_tts.manifest import validate_lines

    line = json.dumps(GOOD, ensure_ascii=False)
    report = validate_lines([line, line])
    assert len(report.entries) == 1
    assert "duplicate id" in report.errors[0].message


def test_missing_and_mistyped_fields():
    record = dict(GOOD, tags="PROSODY")
    del record["quality"]
    errors = _errors(record)
    assert "missing required field 'quality'" in errors
    assert "field 'tags' must be list" in errors


def test_audio_path_traversal_rejected():
    assert _errors(dict(GOOD, audio="${TAM_AUDIO_ROOT}/../secret.wav"))


def test_permissions_validated():
    assert _errors(dict(GOOD, permissions=["publish"]))
    entry, _ = validate_record(dict(GOOD, permissions=["training", "distribution"]))
    assert entry.permissions == ("training", "distribution")


def test_unknown_field_and_tag_warn():
    _, issues = validate_record(dict(GOOD, speaker_name="x", tags=["FOO"]))
    warnings = [i.message for i in issues if i.severity == "warning"]
    assert any("speaker_name" in w for w in warnings)
    assert any("'FOO'" in w for w in warnings)


def test_empty_manifest(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n")
    assert not load_manifest(path).ok
    assert not load_manifest(tmp_path / "missing.jsonl").ok
