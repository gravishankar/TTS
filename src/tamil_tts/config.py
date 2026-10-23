"""Configuration loading and local-root resolution.

Values the PRD does not define are written as "TBD" in configs/*.yaml. Reading one
through `get_value` raises `UndefinedValueError` instead of letting code guess.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TBD = "TBD"
CONFIG_FILES = ("models", "eval", "release_gates")

# Local roots live outside the repository, under $HOME (PRD §7; C2 decision 2).
ROOT_ENV_VARS = {
    "audio": "TAM_AUDIO_ROOT",
    "models": "TAMIL_TTS_MODEL_ROOT",
    "cache": "TAMIL_TTS_CACHE_ROOT",
    "outputs": "TAMIL_TTS_OUTPUT_ROOT",  # experiment run outputs (audio + results)
}


class ConfigError(Exception):
    """A configuration file or local root is missing or malformed."""


class UndefinedValueError(ConfigError):
    """A required value is still marked TBD."""


def is_tbd(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() == TBD


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def load_configs(config_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every project config file from `config_dir`, keyed by file stem."""
    return {name: load_yaml(Path(config_dir) / f"{name}.yaml") for name in CONFIG_FILES}


def get_value(config: Mapping[str, Any], dotted_key: str, *, allow_tbd: bool = False) -> Any:
    """Return `config["a"]["b"]` for "a.b"; refuse TBD values unless `allow_tbd`."""
    node: Any = config
    for part in dotted_key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(f"missing config key: {dotted_key}")
        node = node[part]
    if is_tbd(node) and not allow_tbd:
        raise UndefinedValueError(f"{dotted_key} is TBD; it must be decided before use")
    return node


def find_tbd(config: Any, prefix: str = "") -> list[str]:
    """List the dotted keys whose value is TBD."""
    if isinstance(config, Mapping):
        found: list[str] = []
        for key, value in config.items():
            found.extend(find_tbd(value, f"{prefix}.{key}" if prefix else str(key)))
        return found
    return [prefix] if is_tbd(config) else []


@dataclass(frozen=True)
class LocalRoots:
    audio: Path | None
    models: Path | None
    cache: Path | None
    outputs: Path | None


def resolve_local_roots(
    env: Mapping[str, str] | None = None,
    *,
    required: tuple[str, ...] = ("audio", "models", "cache", "outputs"),
    repo_root: Path | None = None,
    check_exists: bool = True,
) -> LocalRoots:
    """Resolve local data roots from environment variables and fail clearly.

    Every required root must be set, must exist (when `check_exists`), and must not lie
    inside the repository, so recordings, models and caches can never be committed.
    """
    env = os.environ if env is None else env
    repo = repo_root or find_repo_root()
    repo = repo.resolve() if repo else None
    errors: list[str] = []
    resolved: dict[str, Path | None] = {}
    for name, var in ROOT_ENV_VARS.items():
        raw = env.get(var, "").strip()
        if not raw:
            resolved[name] = None
            if name in required:
                errors.append(f"{var} is not set")
            continue
        path = Path(os.path.expanduser(raw)).resolve()
        resolved[name] = path
        if repo is not None and (path == repo or repo in path.parents):
            errors.append(f"{var}={path} is inside the repository; keep it under $HOME instead")
        elif check_exists and name in required and not path.is_dir():
            errors.append(f"{var}={path} does not exist or is not a directory")
    if errors:
        raise ConfigError("local roots are not usable:\n  " + "\n  ".join(errors))
    return LocalRoots(**resolved)


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default: cwd) to the directory holding pyproject.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None
