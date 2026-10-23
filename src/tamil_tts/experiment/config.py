"""Experiment config (`experiments/EXP-xxx/config.yaml`).

experiment: EXP-001
manifest: ${TAM_MANIFEST}            # private manifest on the Mac
frozen_splits: ${TAM_FROZEN_SPLITS}  # frozen split record (ids + splits only)
splits: [test, challenge]
smoke:
  max_utterances: 20                 # or ids: [TAM-001, ...]
systems:
  - id: indicf5-tam-ref
    model: indicf5                   # key in configs/models.yaml
    reference:                       # omitted/null = none; TBD = not chosen yet
      entry_id: TAM-012              # TRAIN/VALIDATE entry from the manifest
    # or: reference: {audio: ${TAMIL_TTS_MODEL_ROOT}/x.wav, transcript: "..."}
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tamil_tts.config import ConfigError, is_tbd
from tamil_tts.manifest import ID_RE, SPLITS

EXPERIMENT_ID_RE = re.compile(r"^EXP-\d{3}$")
SYSTEM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass(frozen=True)
class ReferenceSpec:
    entry_id: str | None = None
    audio: str | None = None  # unexpanded; may contain ${VAR}
    transcript: str | None = None


@dataclass(frozen=True)
class SystemSpec:
    id: str
    model: str
    reference: ReferenceSpec | None = None
    reference_tbd: bool = False


@dataclass(frozen=True)
class SmokeSpec:
    max_utterances: int
    ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExperimentConfig:
    experiment: str
    manifest: str | None
    frozen_splits: str | None
    splits: tuple[str, ...]
    smoke: SmokeSpec
    systems: tuple[SystemSpec, ...]
    sha256: str
    path: Path


def expand_vars(value: str, env: Mapping[str, str] | None = None) -> str:
    """Expand ${VAR} from the environment; fail clearly when one is unset."""
    env = os.environ if env is None else env

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if not env.get(name):
            raise ConfigError(f"{name} is not set (needed for {value!r})")
        return env[name]

    return _VAR_RE.sub(replace, value)


def _reference(raw: Any, system_id: str) -> tuple[ReferenceSpec | None, bool]:
    if raw is None:
        return None, False
    if is_tbd(raw):
        return None, True
    if not isinstance(raw, dict):
        raise ConfigError(f"system {system_id}: reference must be a mapping, null or TBD")
    entry_id, audio, transcript = raw.get("entry_id"), raw.get("audio"), raw.get("transcript")
    if entry_id is not None:
        if audio is not None or transcript is not None:
            raise ConfigError(f"system {system_id}: use entry_id or audio+transcript, not both")
        if not isinstance(entry_id, str) or not ID_RE.match(entry_id):
            raise ConfigError(f"system {system_id}: reference entry_id must look like TAM-001")
        return ReferenceSpec(entry_id=entry_id), False
    if not (isinstance(audio, str) and isinstance(transcript, str) and transcript.strip()):
        raise ConfigError(f"system {system_id}: reference needs audio and transcript")
    return ReferenceSpec(audio=audio, transcript=transcript), False


def load_experiment_config(path: Path, known_models: set[str] | None = None) -> ExperimentConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"experiment config not found: {path}")
    raw_bytes = path.read_bytes()
    try:
        data = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping")

    experiment = data.get("experiment")
    if not isinstance(experiment, str) or not EXPERIMENT_ID_RE.match(experiment):
        raise ConfigError("experiment must look like EXP-001")

    splits = data.get("splits")
    if not isinstance(splits, list) or not splits or any(s not in SPLITS for s in splits):
        raise ConfigError(f"splits must be a non-empty list of {', '.join(SPLITS)}")

    smoke_raw = data.get("smoke") or {}
    max_utterances = smoke_raw.get("max_utterances", 20)
    smoke_ids = smoke_raw.get("ids") or []
    if not isinstance(max_utterances, int) or max_utterances < 1:
        raise ConfigError("smoke.max_utterances must be a positive integer")
    if not all(isinstance(i, str) and ID_RE.match(i) for i in smoke_ids):
        raise ConfigError("smoke.ids must be manifest ids like TAM-001")

    systems_raw = data.get("systems")
    if not isinstance(systems_raw, list) or not systems_raw:
        raise ConfigError("systems must be a non-empty list")
    systems: list[SystemSpec] = []
    for item in systems_raw:
        if not isinstance(item, dict):
            raise ConfigError("each system must be a mapping")
        system_id, model = item.get("id"), item.get("model")
        if not isinstance(system_id, str) or not SYSTEM_ID_RE.match(system_id):
            raise ConfigError(f"invalid system id: {system_id!r}")
        if not isinstance(model, str) or not model:
            raise ConfigError(f"system {system_id}: model is required")
        if known_models is not None and model not in known_models:
            raise ConfigError(f"system {system_id}: unknown model {model!r}")
        reference, tbd = _reference(item.get("reference"), system_id)
        systems.append(SystemSpec(system_id, model, reference, tbd))
    ids = [s.id for s in systems]
    if len(set(ids)) != len(ids):
        raise ConfigError("system ids must be unique")

    def optional_str(key: str) -> str | None:
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"{key} must be a string")
        return value

    return ExperimentConfig(
        experiment=experiment,
        manifest=optional_str("manifest"),
        frozen_splits=optional_str("frozen_splits"),
        splits=tuple(splits),
        smoke=SmokeSpec(max_utterances, tuple(smoke_ids)),
        systems=tuple(systems),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        path=path,
    )
