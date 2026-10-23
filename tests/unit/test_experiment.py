import json
import struct
import wave
from pathlib import Path

import pytest

from tamil_tts.config import ConfigError, load_yaml
from tamil_tts.experiment import (
    ExperimentError,
    RunOptions,
    load_experiment_config,
    run_experiment,
)
from tamil_tts.experiment.config import expand_vars
from tamil_tts.manifest import load_manifest
from tamil_tts.models import ModelIdentity, candidate_models
from tamil_tts.models.base import BaseTTSModel, RuntimeMetadata
from tamil_tts.models.mock import MockTTSModel
from tamil_tts.splits import freeze_splits

REPO = Path(__file__).resolve().parents[2]


class ToneModel(BaseTTSModel):
    """Writes a short non-silent PCM signal so completeness can pass in tests."""

    def __init__(self, reference_audio=True):
        super().__init__(ModelIdentity("tone-test", "0"))
        self._reference_audio = reference_audio
        self.references = []

    def status(self):
        from tamil_tts.models import Availability, ModelStatus

        return ModelStatus(self.identity, Availability.AVAILABLE)

    def supports_reference_audio(self):
        return self._reference_audio

    def _synthesize(self, request):
        self.references.append(request.reference)
        with wave.open(str(request.output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(struct.pack("<2h", 900, -900) * 4000)
        return RuntimeMetadata(wall_time_s=0.0, duration_s=1.0, sample_rate=8000)


@pytest.fixture
def setup(tmp_path, fixtures):
    manifest = fixtures / "manifests" / "valid.jsonl"
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(freeze_splits(load_manifest(manifest).entries)))
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    (audio_root / "TAM-003.wav").write_bytes(b"reference bytes")
    env = {
        "TAM_AUDIO_ROOT": str(audio_root),
        "TAM_MANIFEST": str(manifest),
        "TAM_FROZEN_SPLITS": str(frozen),
    }
    return {"manifest": manifest, "frozen": frozen, "env": env, "tmp": tmp_path}


def _config(tmp_path, systems_yaml: str, extra: str = "") -> Path:
    path = tmp_path / "exp" / "config.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "experiment: EXP-001\nmanifest: ${TAM_MANIFEST}\nfrozen_splits: ${TAM_FROZEN_SPLITS}\n"
        f"splits: [test, challenge]\n{extra}systems:\n{systems_yaml}"
    )
    return path


TWO_SYSTEMS = """  - id: tone
    model: tone
  - id: tone-ref
    model: tone
    reference: {entry_id: TAM-003}
"""


def _run(setup, config_path, factory, **options):
    eval_cfg = load_yaml(REPO / "configs" / "eval.yaml")
    return run_experiment(
        load_experiment_config(config_path),
        options=RunOptions(**options),
        output_root=setup["tmp"] / "outputs",
        cache_root=setup["tmp"] / "cache",
        model_factory=factory,
        eval_config=eval_cfg,
        env=setup["env"],
        repo_root=setup["tmp"] / "repo",
    )


def test_committed_exp001_config_is_valid():
    names = set(candidate_models(load_yaml(REPO / "configs" / "models.yaml")))
    config = load_experiment_config(REPO / "experiments" / "EXP-001" / "config.yaml", names)
    assert [s.id for s in config.systems] == [
        "pocket-tts-tamil",
        "indicf5-standard-ref",
        "indicf5-tam-ref",
        "indic-speak",
    ]
    assert config.splits == ("test", "challenge")


def test_full_run_writes_compact_results(setup):
    model = ToneModel()
    summary = _run(setup, _config(setup["tmp"], TWO_SYSTEMS), lambda spec: model, run_id="r1")
    run_dir = summary.run_dir
    assert run_dir == (setup["tmp"] / "outputs" / "EXP-001" / "r1").resolve()
    for name in ("results.json", "errors.jsonl", "segments.jsonl", "REPORT.md"):
        assert (run_dir / name).is_file()

    results = json.loads((run_dir / "results.json").read_text())
    assert results["inputs"]["utterances"] == 2  # TAM-009 (test), TAM-010 (challenge)
    assert results["inputs"]["segments"] == 2  # one sentence each
    for system in results["systems"]:
        assert system["ran"] and system["segments_ok"] == 2
        assert system["gate_completeness"] == "provisional_pass"
    assert (run_dir / "errors.jsonl").read_text() == ""

    # Reference comes from a TRAIN entry; its transcript is passed but not recorded.
    assert model.references[-1].transcript.startswith("வாழைப்பழம்")
    assert results["systems"][1]["reference"]["entry_id"] == "TAM-003"

    # No Tamil text or personal paths in any committed-style output.
    for name in ("results.json", "errors.jsonl", "segments.jsonl", "REPORT.md"):
        text = (run_dir / name).read_text()
        assert not any("஀" <= ch <= "௿" for ch in text), name
        assert str(setup["tmp"]) not in text, name
    assert (run_dir / "audio" / "tone" / "TAM-010-S01.wav").is_file()


def test_mock_run_fails_completeness_as_silence(setup):
    identity = ModelIdentity("mock:tone", "mock-0")
    summary = _run(
        setup,
        _config(setup["tmp"], TWO_SYSTEMS),
        lambda spec: MockTTSModel(identity=identity),
        mock=True,
        smoke=True,
        run_id="m1",
    )
    system = summary.results["systems"][0]
    assert system["segments_silent"] == 2 and system["gate_completeness"] == "mock_not_evidence"
    report = (summary.run_dir / "REPORT.md").read_text()
    assert "MOCK RUN" in report
    errors = [
        json.loads(line) for line in (summary.run_dir / "errors.jsonl").read_text().splitlines()
    ]
    assert {e["error"] for e in errors} == {"silent"}


def test_cache_reused_across_runs(setup):
    config = _config(setup["tmp"], "  - id: tone\n    model: tone\n")
    model = ToneModel()
    _run(setup, config, lambda spec: model, run_id="a")
    second = _run(setup, config, lambda spec: model, run_id="b")
    system = second.results["systems"][0]
    assert system["segments_cached"] == 2 and system["synthesis_seconds"] == 0
    assert system["real_time_factor"] is None
    third = _run(setup, config, lambda spec: model, run_id="c", use_cache=False)
    assert third.results["systems"][0]["segments_cached"] == 0


def test_existing_run_is_not_overwritten(setup):
    config = _config(setup["tmp"], "  - id: tone\n    model: tone\n")
    _run(setup, config, lambda spec: ToneModel(), run_id="same")
    marker = setup["tmp"] / "outputs" / "EXP-001" / "same" / "results.json"
    before = marker.read_text()
    with pytest.raises(ExperimentError, match="not overwriting"):
        _run(setup, config, lambda spec: ToneModel(), run_id="same")
    assert marker.read_text() == before


def test_unavailable_and_tbd_systems_recorded(setup):
    systems = """  - id: unverified
    model: indicf5
  - id: ref-tbd
    model: tone
    reference: TBD
  - id: no-ref-support
    model: tone
    reference: {entry_id: TAM-003}
"""
    candidates = candidate_models(load_yaml(REPO / "configs" / "models.yaml"))

    def factory(spec):
        if spec.model == "indicf5":
            return candidates["indicf5"]
        return ToneModel(reference_audio=spec.id != "no-ref-support")

    summary = _run(setup, _config(setup["tmp"], systems), factory, run_id="u")
    by_id = {s["system_id"]: s for s in summary.results["systems"]}
    assert "unverified" in by_id["unverified"]["blocked_reason"]
    assert "TBD" in by_id["ref-tbd"]["blocked_reason"]
    assert "reference audio" in by_id["no-ref-support"]["blocked_reason"]
    assert all(s["gate_completeness"] == "not_run" for s in by_id.values())
    errors = (summary.run_dir / "errors.jsonl").read_text().splitlines()
    assert len(errors) == 3


def test_model_errors_recorded_per_segment(setup):
    config = _config(setup["tmp"], "  - id: broken\n    model: x\n")
    summary = _run(setup, config, lambda spec: MockTTSModel(failure="raise"), run_id="e")
    system = summary.results["systems"][0]
    assert system["segments_error"] == 2 and system["gate_completeness"] == "fail"
    rows = [json.loads(x) for x in (summary.run_dir / "segments.jsonl").read_text().splitlines()]
    assert {r["error"] for r in rows} == {"runtime_error"}


def test_frozen_split_violation_aborts(setup):
    frozen = json.loads(setup["frozen"].read_text())
    from tamil_tts.splits import _membership_checksum

    frozen["membership"]["TAM-009"] = "train"
    frozen["checksum"] = _membership_checksum(frozen["membership"])
    setup["frozen"].write_text(json.dumps(frozen))
    with pytest.raises(ExperimentError, match="frozen splits violated"):
        _run(setup, _config(setup["tmp"], TWO_SYSTEMS), lambda spec: ToneModel())
    assert not (setup["tmp"] / "outputs").exists()


def test_missing_frozen_record_aborts(setup):
    setup["frozen"].unlink()
    with pytest.raises(ExperimentError, match="splits freeze"):
        _run(setup, _config(setup["tmp"], TWO_SYSTEMS), lambda spec: ToneModel())


def test_invalid_manifest_aborts(setup, fixtures):
    setup["env"]["TAM_MANIFEST"] = str(fixtures / "manifests" / "invalid.jsonl")
    with pytest.raises(ExperimentError, match="manifest is invalid"):
        _run(setup, _config(setup["tmp"], TWO_SYSTEMS), lambda spec: ToneModel())


def test_protected_reference_rejected(setup):
    systems = "  - id: bad\n    model: tone\n    reference: {entry_id: TAM-009}\n"
    with pytest.raises(ExperimentError, match="TEST/CHALLENGE"):
        _run(setup, _config(setup["tmp"], systems), lambda spec: ToneModel())


def test_smoke_ids_and_limit(setup):
    config = _config(setup["tmp"], "  - id: tone\n    model: tone\n", "smoke:\n  ids: [TAM-010]\n")
    summary = _run(setup, config, lambda spec: ToneModel(), smoke=True, run_id="s")
    assert summary.results["inputs"]["utterances"] == 1 and summary.results["mode"] == "smoke"
    bad = _config(setup["tmp"], "  - id: tone\n    model: tone\n", "smoke:\n  ids: [TAM-001]\n")
    with pytest.raises(ExperimentError, match="smoke ids"):
        _run(setup, bad, lambda spec: ToneModel(), smoke=True)


def test_output_root_inside_repo_rejected(setup):
    repo = setup["tmp"] / "repo"
    eval_cfg = load_yaml(REPO / "configs" / "eval.yaml")
    with pytest.raises(ExperimentError, match="inside the repository"):
        run_experiment(
            load_experiment_config(_config(setup["tmp"], TWO_SYSTEMS)),
            options=RunOptions(),
            output_root=repo / "out",
            cache_root=setup["tmp"] / "cache",
            model_factory=lambda spec: ToneModel(),
            eval_config=eval_cfg,
            env=setup["env"],
            repo_root=repo,
        )


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("experiment: EXP-1\nsplits: [test]\nsystems: [{id: a, model: m}]\n", "EXP-001"),
        ("experiment: EXP-001\nsplits: [holdout]\nsystems: [{id: a, model: m}]\n", "splits"),
        ("experiment: EXP-001\nsplits: [test]\nsystems: []\n", "non-empty"),
        ("experiment: EXP-001\nsplits: [test]\nsystems: [{id: A!, model: m}]\n", "system id"),
        (
            "experiment: EXP-001\nsplits: [test]\n"
            "systems: [{id: a, model: m}, {id: a, model: m}]\n",
            "unique",
        ),
        (
            "experiment: EXP-001\nsplits: [test]\nsystems: [{id: a, model: m, reference: x}]\n",
            "reference",
        ),
        ("experiment: EXP-001\nsplits: [test]\nsystems: [{id: a, model: zzz}]\n", "unknown model"),
    ],
)
def test_config_validation(tmp_path, body, message):
    path = tmp_path / "c.yaml"
    path.write_text(body)
    with pytest.raises(ConfigError, match=message):
        load_experiment_config(path, {"m"})


def test_expand_vars():
    assert expand_vars("${A}/x", {"A": "/root"}) == "/root/x"
    with pytest.raises(ConfigError, match="B is not set"):
        expand_vars("${B}/x", {})
