import json
from pathlib import Path

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
    assert "indic-speak: ran; 0/2 ok; completeness gate mock_not_evidence" in out
    assert "pocket-tts-tamil: not run (reference prompt not selected yet (TBD))" in out
    assert main(args) == 2  # same run id: never overwritten
    assert main(["experiment", "status", "EXP-001"]) == 0
    assert "cli-test: complete" in capsys.readouterr().out


def test_audio_inspect(tmp_path, capsys):
    import struct
    import wave

    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(struct.pack("<2h", 500, -500) * 12000)
    assert main(["audio", "inspect", str(path), "--elapsed", "0.5"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["duration_s"] == 1.0 and data["real_time_factor"] == 0.5
    assert data["status"] == "ok" and data["sample_rate"] == 24000

    silent = tmp_path / "s.wav"
    with wave.open(str(silent), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 100)
    assert main(["audio", "inspect", str(silent)]) == 1
    (tmp_path / "bad.wav").write_bytes(b"nope")
    assert main(["audio", "inspect", str(tmp_path / "bad.wav")]) == 1


def test_listen_export_and_guards(tmp_path, monkeypatch, capsys):
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from listening_fixtures import make_run

    run_dir = make_run(tmp_path)
    monkeypatch.setenv("TAMIL_TTS_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.delenv("TAM_MANIFEST", raising=False)
    assert main(["listen", "export", "EXP-001", "--run", "r1", "--export-id", "x1"]) == 0
    assert (run_dir / "listening" / "exports" / "x1" / "listener_results.jsonl").is_file()
    assert main(["listen", "export", "EXP-001", "--run", "r1", "--export-id", "x1"]) == 2
    assert main(["listen", "export", "EXP-001", "--run", "latest", "--export-id", "x2"]) == 0
    assert main(["listen", "export", "EXP-001", "--run", "../r1"]) == 2
    base = ["listen", "serve", "EXP-001", "--run", "r1", "--port", "0"]
    assert main([*base, "--reviewer", "Geetha", "--mode", "blind"]) == 2  # names refused
    assert main([*base, "--reviewer", "REV-01", "--mode", "text"]) == 2  # no manifest
    err = capsys.readouterr().err
    assert "pseudonymous" in err and "private manifest" in err

    mock_root = tmp_path / "mockroot"
    mock_root.mkdir()
    make_run(mock_root, mock=True, run_id="m1")
    monkeypatch.setenv("TAMIL_TTS_OUTPUT_ROOT", str(mock_root / "outputs"))
    serve_mock = ["listen", "serve", "EXP-001", "--run", "m1", "--port", "0"]
    assert main([*serve_mock, "--reviewer", "REV-01", "--mode", "blind"]) == 2
    assert "mock audio cannot enter" in capsys.readouterr().err
