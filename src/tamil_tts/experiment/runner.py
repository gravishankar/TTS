"""Local experiment runner (PRD §13).

validate config + manifest → enforce frozen splits → normalize + segment → check model
availability → synthesize through the common interface (with cache) → check every
segment's audio → write segments.jsonl, errors.jsonl, results.json, REPORT.md.

Everything is written to a new run directory under $TAMIL_TTS_OUTPUT_ROOT, outside the
repository; an existing run directory is never reused. Result files hold ids,
checksums, counts and timings only — never Tamil text, transcripts or personal paths —
so they can be reviewed and committed back without exposing private data.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tamil_tts import __version__
from tamil_tts.cache import SynthesisCache
from tamil_tts.config import ConfigError, find_repo_root, get_value, is_tbd
from tamil_tts.eval.completeness import SegmentAudioStatus, check_segment_audio
from tamil_tts.eval.report import render_report
from tamil_tts.experiment.config import ExperimentConfig, SystemSpec, expand_vars
from tamil_tts.frontend import Normalizer, SegmentationError, segment_text
from tamil_tts.frontend.segment import Segment
from tamil_tts.manifest import PROTECTED_SPLITS, ManifestEntry, load_manifest
from tamil_tts.models.base import ReferenceAudio, SynthesisRequest, TTSModel, file_sha256
from tamil_tts.splits import check_frozen, check_leakage

RESULTS_FORMAT_VERSION = 1
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_REPORTED_ISSUES = 10

ModelFactory = Callable[[SystemSpec], TTSModel]


class ExperimentError(Exception):
    """The experiment cannot start: invalid inputs, frozen-split violation, or bad config."""


@dataclass(frozen=True)
class RunOptions:
    smoke: bool = False
    mock: bool = False
    use_cache: bool = True
    run_id: str | None = None
    manifest: Path | None = None
    frozen_splits: Path | None = None


@dataclass
class RunSummary:
    run_dir: Path
    results: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Inputs:
    entries: dict[str, ManifestEntry]
    selected: list[ManifestEntry]
    segments: list[tuple[ManifestEntry, Segment]]
    manifest_sha256: str
    frozen_checksum: str
    warnings: list[str]


def _issues_text(issues: list[Any]) -> str:
    shown = "\n  ".join(str(i) for i in issues[:MAX_REPORTED_ISSUES])
    more = len(issues) - MAX_REPORTED_ISSUES
    return shown + (f"\n  ... and {more} more" if more > 0 else "")


def _resolve_path(override: Path | None, configured: str | None, what: str, env) -> Path:
    if override is not None:
        return Path(override)
    if configured is None:
        raise ExperimentError(f"no {what} given in the experiment config or on the command line")
    try:
        return Path(expand_vars(configured, env)).expanduser()
    except ConfigError as exc:
        raise ExperimentError(str(exc)) from exc


def _prepare_inputs(
    config: ExperimentConfig, options: RunOptions, eval_config: Mapping[str, Any], env
) -> _Inputs:
    manifest_path = _resolve_path(options.manifest, config.manifest, "manifest", env)
    report = load_manifest(manifest_path)
    if not report.ok:
        raise ExperimentError("manifest is invalid:\n  " + _issues_text(report.errors))

    frozen_path = _resolve_path(
        options.frozen_splits, config.frozen_splits, "frozen split record", env
    )
    if not frozen_path.is_file():
        raise ExperimentError(
            f"frozen split record not found: {frozen_path}. "
            "Create it once with `tamil-tts splits freeze` before running EXP-001."
        )
    try:
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ExperimentError(f"frozen split record is not valid JSON: {exc}") from exc
    frozen_issues = check_frozen(report.entries, frozen)
    if frozen_issues:
        raise ExperimentError("frozen splits violated:\n  " + _issues_text(frozen_issues))

    threshold = get_value(eval_config, "leakage.near_duplicate_threshold", allow_tbd=True)
    leakage = check_leakage(report.entries, None if is_tbd(threshold) else float(threshold))
    leak_errors = [i for i in leakage if i.severity == "error"]
    if leak_errors:
        raise ExperimentError("split leakage:\n  " + _issues_text(leak_errors))
    warnings = [str(i) for i in report.warnings + [i for i in leakage if i.severity != "error"]]

    entries = {e.id: e for e in report.entries}
    selected = sorted((e for e in report.entries if e.split in config.splits), key=lambda e: e.id)
    if options.smoke:
        if config.smoke.ids:
            pool = {e.id: e for e in selected}
            missing = [i for i in config.smoke.ids if i not in pool]
            if missing:
                raise ExperimentError(f"smoke ids not in selected splits: {', '.join(missing)}")
            selected = [pool[i] for i in config.smoke.ids]
        else:
            selected = selected[: config.smoke.max_utterances]
    if not selected:
        raise ExperimentError(f"no manifest entries in splits {list(config.splits)}")

    max_chars = get_value(eval_config, "segmentation.max_chars", allow_tbd=True)
    max_chars = None if is_tbd(max_chars) else int(max_chars)
    segments: list[tuple[ManifestEntry, Segment]] = []
    for entry in selected:
        try:
            for seg in segment_text(entry.id, entry.text, max_chars=max_chars):
                segments.append((entry, seg))
        except SegmentationError as exc:
            raise ExperimentError(f"segmentation failed: {exc}") from exc

    return _Inputs(
        entries=entries,
        selected=selected,
        segments=segments,
        manifest_sha256=file_sha256(manifest_path),
        frozen_checksum=str(frozen.get("checksum")),
        warnings=warnings,
    )


def _resolve_reference(
    spec: SystemSpec, entries: Mapping[str, ManifestEntry], env
) -> tuple[ReferenceAudio | None, str | None, dict[str, Any] | None]:
    """Return (reference, blocked_reason, commit-safe reference info)."""
    if spec.reference_tbd:
        return None, "reference prompt not selected yet (TBD)", None
    ref = spec.reference
    if ref is None:
        return None, None, None
    if ref.entry_id is not None:
        entry = entries.get(ref.entry_id)
        if entry is None:
            raise ExperimentError(f"system {spec.id}: reference {ref.entry_id} not in manifest")
        if entry.split in PROTECTED_SPLITS:
            raise ExperimentError(
                f"system {spec.id}: reference {ref.entry_id} is in {entry.split}; "
                "TEST/CHALLENGE recordings may not be used as prompts"
            )
        audio_spec, transcript = entry.audio, entry.text
    else:
        audio_spec, transcript = ref.audio or "", ref.transcript or ""
    try:
        audio = Path(expand_vars(audio_spec, env)).expanduser()
    except ConfigError as exc:
        return None, f"reference audio unavailable: {exc}", None
    if not audio.is_file():
        return None, "reference audio file not found", None
    reference = ReferenceAudio.from_file(audio, transcript)
    info = {
        "entry_id": ref.entry_id,
        "audio_sha256": reference.checksum,
        "transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
    }
    return reference, None, info


def _new_run_dir(output_root: Path, experiment: str, run_id: str, repo_root: Path | None) -> Path:
    root = Path(output_root).expanduser().resolve()
    repo = repo_root.resolve() if repo_root else None
    if repo is not None and (root == repo or repo in root.parents):
        raise ExperimentError(f"output root {root} is inside the repository; use $HOME")
    if not RUN_ID_RE.match(run_id):
        raise ExperimentError(f"invalid run id: {run_id!r}")
    run_dir = root / experiment / run_id
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise ExperimentError(f"run directory already exists, not overwriting: {run_dir}") from exc
    return run_dir


def _check_states(eval_config: Mapping[str, Any]) -> dict[str, str]:
    def state(key: str, label: str) -> str:
        value = get_value(eval_config, key, allow_tbd=True)
        return f"not evaluated: {key} is TBD" if is_tbd(value) else f"not implemented: {label}"

    return {
        "audio_present_and_readable": "evaluated",
        "digital_silence": "evaluated",
        "duration_sanity": state("sanity_checks.duration", "duration check"),
        "near_silence": state("sanity_checks.silence", "near-silence check"),
        "asr": state("asr.model", "ASR comparison"),
    }


def _run_system(
    spec: SystemSpec,
    model: TTSModel,
    inputs: _Inputs,
    run_dir: Path,
    cache: SynthesisCache | None,
    env,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    status = model.status()
    summary: dict[str, Any] = {
        "system_id": spec.id,
        "model": model.version_info(),
        "availability": status.availability.value,
        "reason": status.reason,
        "reference": None,
        "segments_total": len(inputs.segments),
    }
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    blocked = None if status.available else f"model {status.availability.value}: {status.reason}"
    reference = None
    if blocked is None:
        reference, blocked, summary["reference"] = _resolve_reference(spec, inputs.entries, env)
    if blocked is None and reference is not None and not model.supports_reference_audio():
        blocked = "model does not accept reference audio"
    if blocked is not None:
        summary.update(ran=False, blocked_reason=blocked, segments_ok=0, completeness=0.0)
        summary["gate_completeness"] = "not_run"
        errors.append(
            {
                "system_id": spec.id,
                "model": model.identity.model_id,
                "error": "not_run",
                "message": blocked,
                "segments": len(inputs.segments),
            }
        )
        return summary, rows, errors

    audio_dir = run_dir / "audio" / spec.id
    counts: Counter[str] = Counter()
    audio_seconds = synth_seconds = synth_audio_seconds = 0.0
    peak_memory: int | None = None
    for entry, seg in inputs.segments:
        output = audio_dir / f"{seg.segment_id}.wav"
        request = SynthesisRequest(seg.segment_id, seg.segment_text, output, reference)
        result = cache.synthesize(model, request) if cache else model.synthesize(request)
        meta = result.metadata
        if result.ok:
            check = check_segment_audio(result.output_path)
            status_value = check.status.value
            error_code, message, duration = None, check.message, check.duration_s
        else:
            status_value = "error"
            error_code, message, duration = result.error.code.value, result.error.message, None
        counts[status_value] += 1
        counts["cached"] += int(result.cached)
        if duration:
            audio_seconds += duration
            if not result.cached and meta is not None:
                synth_seconds += meta.wall_time_s
                synth_audio_seconds += duration
        if meta is not None and meta.peak_memory_bytes is not None:
            peak_memory = max(peak_memory or 0, meta.peak_memory_bytes)

        row = {
            "system_id": spec.id,
            "segment_id": seg.segment_id,
            "id": entry.id,
            "split": entry.split,
            "tags": list(entry.tags),
            "segment_sha256": seg.checksum,
            "expected_length": seg.expected_length,
            "status": status_value,
            "error": error_code,
            "message": message,
            "cached": result.cached,
            "duration_s": duration,
            "wall_time_s": meta.wall_time_s if meta else None,
            "audio": str(output.relative_to(run_dir)) if result.ok else None,
        }
        rows.append(row)
        if status_value != SegmentAudioStatus.OK.value:
            errors.append(
                {
                    "system_id": spec.id,
                    "model": model.identity.model_id,
                    "segment_id": seg.segment_id,
                    "id": entry.id,
                    "split": entry.split,
                    "tags": list(entry.tags),
                    "error": error_code or status_value,
                    "message": message,
                }
            )

    total = len(inputs.segments)
    ok = counts[SegmentAudioStatus.OK.value]
    summary.update(
        ran=True,
        blocked_reason=None,
        segments_ok=ok,
        segments_silent=counts[SegmentAudioStatus.SILENT.value],
        segments_error=counts["error"],
        segments_bad_audio=sum(
            counts[s.value]
            for s in (
                SegmentAudioStatus.MISSING,
                SegmentAudioStatus.INVALID,
                SegmentAudioStatus.EMPTY,
            )
        ),
        segments_cached=counts["cached"],
        completeness=ok / total if total else 0.0,
        audio_seconds=round(audio_seconds, 3),
        synthesis_seconds=round(synth_seconds, 3),
        real_time_factor=round(synth_seconds / synth_audio_seconds, 4)
        if synth_audio_seconds
        else None,
        peak_memory_bytes=peak_memory,
        gate_completeness="pass" if total and ok == total else "fail",
    )
    return summary, rows, errors


def run_experiment(
    config: ExperimentConfig,
    *,
    options: RunOptions,
    output_root: Path,
    cache_root: Path | None,
    model_factory: ModelFactory,
    eval_config: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> RunSummary:
    env = os.environ if env is None else env
    repo_root = repo_root or find_repo_root()
    started = datetime.now(UTC)

    inputs = _prepare_inputs(config, options, eval_config, env)
    models = {spec.id: model_factory(spec) for spec in config.systems}

    default_id = started.strftime("%Y%m%dT%H%M%SZ")
    default_id += "-smoke" if options.smoke else ""
    default_id += "-mock" if options.mock else ""
    run_dir = _new_run_dir(output_root, config.experiment, options.run_id or default_id, repo_root)
    cache = None
    if options.use_cache:
        if cache_root is None:
            raise ExperimentError("cache root is required unless caching is disabled")
        cache = SynthesisCache(cache_root, repo_root=repo_root)

    systems, rows, errors = [], [], []
    for spec in config.systems:
        summary, sys_rows, sys_errors = _run_system(
            spec, models[spec.id], inputs, run_dir, cache, env
        )
        systems.append(summary)
        rows += sys_rows
        errors += sys_errors

    try:
        config_ref = str(config.path.resolve().relative_to(repo_root.resolve()))
    except (ValueError, AttributeError):
        config_ref = config.path.name
    results = {
        "format_version": RESULTS_FORMAT_VERSION,
        "experiment": config.experiment,
        "run_id": run_dir.name,
        "mode": "smoke" if options.smoke else "full",
        "mock": options.mock,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            "tamil_tts": __version__,
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "inputs": {
            "config": config_ref,
            "config_sha256": config.sha256,
            "manifest_sha256": inputs.manifest_sha256,
            "frozen_splits_checksum": inputs.frozen_checksum,
            "normalizer_version": Normalizer().version,
            "splits": list(config.splits),
            "utterances": len(inputs.selected),
            "segments": len(inputs.segments),
            "utterances_by_split": dict(Counter(e.split for e in inputs.selected)),
            "cache": "enabled" if cache else "disabled",
        },
        "checks": _check_states(eval_config),
        "systems": systems,
        "gates": {
            "completeness": {s["system_id"]: s["gate_completeness"] for s in systems},
            "frozen_regression": "not evaluated: needs a baseline run; max_regression is TBD",
            "pronunciation_errors": "not evaluated: needs human adjudication",
            "challenge_intelligibility": "not evaluated: needs human listening",
            "comfort": "not evaluated: needs human listening",
        },
        "warnings": inputs.warnings,
    }

    def write_jsonl(name: str, records: list[dict[str, Any]]) -> None:
        lines = (json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records)
        (run_dir / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

    write_jsonl("segments.jsonl", rows)
    write_jsonl("errors.jsonl", errors)
    (run_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "REPORT.md").write_text(render_report(results, errors), encoding="utf-8")
    return RunSummary(run_dir, results, inputs.warnings)
