"""Synthetic experiment runs for listening tests (fictional text, synthetic audio only)."""

import json
import struct
import wave
from pathlib import Path

from tamil_tts.config import load_yaml
from tamil_tts.experiment import RunOptions, load_experiment_config, run_experiment
from tamil_tts.manifest import load_manifest
from tamil_tts.models import Availability, ModelIdentity, ModelStatus
from tamil_tts.models.base import BaseTTSModel, RuntimeMetadata
from tamil_tts.models.mock import MockTTSModel
from tamil_tts.splits import freeze_splits

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
MANIFEST = FIXTURES / "manifests" / "valid.jsonl"


class SyntheticModel(BaseTTSModel):
    """Writes a synthetic square wave, or digital silence when `silent`."""

    def __init__(self, name: str, silent: bool = False):
        super().__init__(ModelIdentity(name, "0"))
        self.silent = silent

    def status(self):
        return ModelStatus(self.identity, Availability.AVAILABLE)

    def supports_reference_audio(self):
        return False

    def _synthesize(self, request):
        sample = 0 if self.silent else 1500
        with wave.open(str(request.output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(struct.pack("<2h", sample, -sample) * 4000)
        return RuntimeMetadata(wall_time_s=0.0, duration_s=1.0, sample_rate=8000)


def make_run(tmp_path: Path, *, mock: bool = False, run_id: str = "r1") -> Path:
    """Create a run with real, silent, failed, missing and invalid audio (or a mock run)."""
    frozen = tmp_path / "frozen.json"
    if not frozen.exists():
        frozen.write_text(json.dumps(freeze_splits(load_manifest(MANIFEST).entries)))
    config = tmp_path / "exp" / "config.yaml"
    config.parent.mkdir(exist_ok=True)
    config.write_text(
        "experiment: EXP-001\nmanifest: ${TAM_MANIFEST}\nfrozen_splits: ${TAM_FROZEN_SPLITS}\n"
        "splits: [test, challenge]\nsystems:\n"
        "  - {id: tone-a, model: a}\n  - {id: tone-b, model: b}\n"
        "  - {id: quiet, model: q}\n  - {id: broken, model: x}\n"
    )
    models = {
        "tone-a": SyntheticModel("tone-a"),
        "tone-b": SyntheticModel("tone-b"),
        "quiet": SyntheticModel("quiet", silent=True),
        "broken": MockTTSModel(identity=ModelIdentity("broken-test", "0"), failure="raise"),
    }

    def factory(spec):
        if mock:
            return MockTTSModel(identity=ModelIdentity(f"mock:{spec.model}", "mock-0"))
        return models[spec.id]

    summary = run_experiment(
        load_experiment_config(config),
        options=RunOptions(mock=mock, run_id=run_id, use_cache=False),
        output_root=tmp_path / "outputs",
        cache_root=None,
        model_factory=factory,
        eval_config=load_yaml(REPO / "configs" / "eval.yaml"),
        env={"TAM_MANIFEST": str(MANIFEST), "TAM_FROZEN_SPLITS": str(frozen)},
        repo_root=tmp_path / "repo",
    )
    run_dir = summary.run_dir
    if not mock:
        (run_dir / "audio" / "tone-b" / "TAM-009-S01.wav").unlink()  # -> missing
        (run_dir / "audio" / "tone-b" / "TAM-010-S01.wav").write_bytes(b"RIFF....junk")  # invalid
    return run_dir


def scales():
    return load_yaml(REPO / "configs" / "listening.yaml")
