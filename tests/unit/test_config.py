import pytest

from tamil_tts.config import (
    ConfigError,
    UndefinedValueError,
    find_tbd,
    get_value,
    is_tbd,
    load_configs,
    load_yaml,
    resolve_local_roots,
)


def test_project_configs_load(config_dir):
    configs = load_configs(config_dir)
    assert set(configs) == {"models", "eval", "release_gates"}
    assert get_value(configs["eval"], "audio_format") == "wav"
    assert set(configs["models"]["models"]) == {"pocket-tts-tamil", "indicf5", "indic-speak"}


def test_undefined_thresholds_stay_tbd(config_dir):
    configs = load_configs(config_dir)
    assert "asr.model" in find_tbd(configs["eval"])
    assert "gates.frozen_regression.max_regression" in find_tbd(configs["release_gates"])
    with pytest.raises(UndefinedValueError):
        get_value(configs["eval"], "segmentation.max_chars")
    assert is_tbd(get_value(configs["eval"], "segmentation.max_chars", allow_tbd=True))


def test_no_model_is_marked_verified(config_dir):
    models = load_configs(config_dir)["models"]["models"]
    assert all(m["verified"] is False for m in models.values())


def test_missing_key_and_bad_files(tmp_path):
    with pytest.raises(ConfigError, match="missing config key"):
        get_value({"a": {}}, "a.b")
    with pytest.raises(ConfigError, match="not found"):
        load_yaml(tmp_path / "nope.yaml")
    bad = tmp_path / "list.yaml"
    bad.write_text("- 1\n- 2\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_yaml(bad)


def _env(audio, models, cache):
    return {
        "TAM_AUDIO_ROOT": str(audio),
        "TAMIL_TTS_MODEL_ROOT": str(models),
        "TAMIL_TTS_CACHE_ROOT": str(cache),
    }


def test_resolve_local_roots_ok(tmp_path):
    repo, home = tmp_path / "repo", tmp_path / "home"
    dirs = [home / n for n in ("audio", "models", "cache")]
    for d in (repo, *dirs):
        d.mkdir(parents=True)
    roots = resolve_local_roots(_env(*dirs), repo_root=repo)
    assert roots.audio == dirs[0].resolve()


def test_resolve_local_roots_fails_clearly(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    with pytest.raises(ConfigError) as exc:
        resolve_local_roots(
            {"TAM_AUDIO_ROOT": str(repo / "data"), "TAMIL_TTS_MODEL_ROOT": str(tmp_path / "x")},
            repo_root=repo,
        )
    message = str(exc.value)
    assert "inside the repository" in message
    assert "does not exist" in message
    assert "TAMIL_TTS_CACHE_ROOT is not set" in message
