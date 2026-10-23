import json

from tamil_tts.cli import main


def test_manifest_validate(fixtures, capsys):
    assert main(["manifest", "validate", str(fixtures / "manifests" / "valid.jsonl")]) == 0
    assert main(["manifest", "validate", str(fixtures / "manifests" / "invalid.jsonl")]) == 1
    assert "error(s)" in capsys.readouterr().err


def test_splits_check_and_freeze(fixtures, config_dir, tmp_path, capsys):
    manifest = str(fixtures / "manifests" / "valid.jsonl")
    common = ["--config-dir", str(config_dir)]
    assert main([*common, "splits", "check", manifest]) == 0
    assert '"train": 7' in capsys.readouterr().out
    assert main([*common, "splits", "check", manifest, "--strict"]) == 1  # TBD warning

    out = tmp_path / "frozen.json"
    assert main(["splits", "freeze", manifest, "--out", str(out)]) == 0
    assert main(["splits", "freeze", manifest, "--out", str(out)]) == 1  # never overwrite
    assert main([*common, "splits", "check", manifest, "--frozen", str(out)]) == 0


def test_text_normalize_and_segment(fixtures, config_dir, capsys):
    assert main(["text", "normalize", "  அப்பா  25 ரூபாய் "]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["normalized_text"] == "அப்பா 25 ரூபாய்"
    assert data["unexpanded_numbers"] == [[6, 8, "25"]]

    path = fixtures / "text" / "smoke_original.txt"
    args = ["--config-dir", str(config_dir), "text", "segment", "--file", str(path), "--id", "T-1"]
    assert main(args) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert [json.loads(line)["segment_id"] for line in lines][-1] == "T-1-S04"


def test_config_show(config_dir, capsys):
    assert main(["--config-dir", str(config_dir), "config", "show"]) == 0
    assert "asr.model" in json.loads(capsys.readouterr().out)["eval"]


def test_env_check_fails_clearly(monkeypatch, capsys):
    for var in (
        "TAM_AUDIO_ROOT",
        "TAMIL_TTS_MODEL_ROOT",
        "TAMIL_TTS_CACHE_ROOT",
        "TAMIL_TTS_OUTPUT_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)
    assert main(["env", "check"]) == 2
    assert "TAM_AUDIO_ROOT is not set" in capsys.readouterr().err


def test_models_status(config_dir, capsys):
    assert main(["--config-dir", str(config_dir), "models", "status"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {v["availability"] for v in data.values()} == {"unverified"}


def test_experiment_run_mock_smoke(fixtures, config_dir, tmp_path, monkeypatch, capsys):
    manifest = fixtures / "manifests" / "valid.jsonl"
    frozen = tmp_path / "frozen.json"
    assert main(["splits", "freeze", str(manifest), "--out", str(frozen)]) == 0
    monkeypatch.setenv("TAMIL_TTS_OUTPUT_ROOT", str(tmp_path / "out"))
    monkeypatch.setenv("TAMIL_TTS_CACHE_ROOT", str(tmp_path / "cache"))
    (tmp_path / "out").mkdir()
    (tmp_path / "cache").mkdir()
    experiments = config_dir.parent / "experiments"
    args = [
        "--config-dir",
        str(config_dir),
        "experiment",
        "run",
        "EXP-001",
        "--smoke",
        "--mock",
        "--manifest",
        str(manifest),
        "--frozen",
        str(frozen),
        "--experiments-dir",
        str(experiments),
        "--run-id",
        "cli-test",
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "indic-speak: ran; 0/2 ok; completeness gate fail" in out  # silent mock audio
    assert "pocket-tts-tamil: not run (reference prompt not selected yet (TBD))" in out
    assert main(args) == 2  # same run id: never overwritten
    assert main(["experiment", "status", "EXP-001"]) == 0
    assert "cli-test: complete" in capsys.readouterr().out
