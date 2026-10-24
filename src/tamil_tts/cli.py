"""`tamil-tts` command-line interface.

Implemented: config, env, models, experiment (run, status), listen (serve, export), audio,
verify, manifest, splits and text commands. Eval report, compare and release-check (PRD §12)
are not implemented yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from tamil_tts import __version__
from tamil_tts.config import (
    ConfigError,
    find_tbd,
    get_value,
    is_tbd,
    load_configs,
    load_yaml,
    resolve_local_roots,
)
from tamil_tts.eval.completeness import AudioCheckError, check_segment_audio, inspect_wav
from tamil_tts.experiment import (
    ExperimentError,
    RunOptions,
    load_experiment_config,
    run_experiment,
)
from tamil_tts.frontend import Normalizer, SegmentationError, segment_text
from tamil_tts.frontend.normalize import find_unexpanded_numbers
from tamil_tts.listening.app import ListeningApp, make_server
from tamil_tts.listening.items import (
    RunLoadError,
    attach_text,
    for_session,
    load_run,
    ordered,
)
from tamil_tts.listening.report import ExportError
from tamil_tts.listening.report import export as export_listening
from tamil_tts.listening.store import SessionError, open_session
from tamil_tts.manifest import Issue, load_manifest
from tamil_tts.models import ModelIdentity, candidate_models
from tamil_tts.models.mock import MockTTSModel
from tamil_tts.splits import check_frozen, check_leakage, freeze_splits, split_counts, split_shares
from tamil_tts.verification import validate_verification_result


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _report(issues: list[Issue], strict: bool) -> int:
    for issue in issues:
        print(issue, file=sys.stderr)
    errors = sum(i.severity == "error" for i in issues)
    warnings = len(issues) - errors
    print(f"{errors} error(s), {warnings} warning(s)", file=sys.stderr)
    return 1 if errors or (strict and warnings) else 0


def _read_text(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text is None:
        raise ConfigError("give TEXT or --file")
    return args.text


def cmd_config_show(args: argparse.Namespace) -> int:
    configs = load_configs(args.config_dir)
    _print_json({name: find_tbd(cfg) for name, cfg in configs.items()})
    return 0


def cmd_env_check(args: argparse.Namespace) -> int:
    roots = resolve_local_roots()
    _print_json({k: str(v) for k, v in asdict(roots).items()})
    return 0


def cmd_models_status(args: argparse.Namespace) -> int:
    models_cfg = load_yaml(Path(args.config_dir) / "models.yaml")
    report = {}
    for name, model in candidate_models(models_cfg).items():
        status = model.status()
        report[name] = {"availability": status.availability.value, "reason": status.reason}
    _print_json(report)
    return 0


def cmd_experiment_run(args: argparse.Namespace) -> int:
    models_cfg = load_yaml(Path(args.config_dir) / "models.yaml")
    eval_cfg = load_yaml(Path(args.config_dir) / "eval.yaml")
    candidates = candidate_models(models_cfg)
    config = load_experiment_config(
        Path(args.experiments_dir) / args.experiment / "config.yaml", set(candidates)
    )
    if args.mock:

        def factory(spec):
            identity = ModelIdentity(f"mock:{spec.model}", "mock-0", license="test-only")
            return MockTTSModel(identity=identity)
    else:

        def factory(spec):
            return candidates[spec.model]

    required = ("outputs",) if args.no_cache else ("outputs", "cache")
    roots = resolve_local_roots(required=required)
    summary = run_experiment(
        config,
        options=RunOptions(
            smoke=args.smoke,
            mock=args.mock,
            use_cache=not args.no_cache,
            run_id=args.run_id,
            manifest=args.manifest,
            frozen_splits=args.frozen,
        ),
        output_root=roots.outputs,
        cache_root=roots.cache,
        model_factory=factory,
        eval_config=eval_cfg,
    )
    for system in summary.results["systems"]:
        state = "ran" if system["ran"] else f"not run ({system['blocked_reason']})"
        print(
            f"{system['system_id']}: {state}; {system['segments_ok']}/"
            f"{system['segments_total']} ok; completeness gate {system['gate_completeness']}"
        )
    print(f"results: {summary.run_dir}")
    return 0


def cmd_experiment_status(args: argparse.Namespace) -> int:
    roots = resolve_local_roots(required=("outputs",))
    base = roots.outputs / args.experiment
    runs = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    if not runs:
        print(f"no runs for {args.experiment} under {base}")
    for run in runs:
        state = "complete" if (run / "results.json").is_file() else "incomplete"
        print(f"{run.name}: {state}")
    return 0


def _run_dir(experiment: str, run: str) -> Path:
    roots = resolve_local_roots(required=("outputs",))
    base = roots.outputs / experiment
    if run == "latest":
        runs = sorted(p for p in base.glob("*") if (p / "results.json").is_file())
        if not runs:
            raise RunLoadError(f"no complete runs for {experiment}")
        return runs[-1]
    if "/" in run or run.startswith("."):
        raise RunLoadError("run must be a run id, not a path")
    return base / run


def cmd_listen_serve(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.experiment, args.run)
    results, items = load_run(run_dir)
    items, excluded_mock = for_session(results, items)  # mock audio never enters a session
    scales = load_yaml(Path(args.config_dir) / "listening.yaml")
    manifest = args.manifest or os.environ.get("TAM_MANIFEST")
    if args.mode == "text" and not manifest:
        raise ConfigError("text mode needs the private manifest: --manifest or TAM_MANIFEST")
    if manifest:
        # Text mode shows it; blind mode reveals it only after each item is rated.
        eval_cfg = load_yaml(Path(args.config_dir) / "eval.yaml")
        max_chars = get_value(eval_cfg, "segmentation.max_chars", allow_tbd=True)
        items = attach_text(items, Path(manifest), None if is_tbd(max_chars) else int(max_chars))
    session, resumed = open_session(
        run_dir,
        experiment=results["experiment"],
        run_id=results["run_id"],
        reviewer_id=args.reviewer,
        mode=args.mode,
        session_id=args.session,
    )
    app = ListeningApp(
        results=results,
        items=ordered(items, session.meta["order_seed"]),
        session=session,
        scales=scales,
        excluded_mock=excluded_mock,
    )
    server = make_server(app, args.port)
    port = server.server_address[1]
    state = app.state()["progress"]
    print(f"{'Resumed' if resumed else 'New'} session {session.session_id} ({args.mode} mode)")
    print(f"{state['rated']}/{state['rateable']} rateable items rated; {state['total']} items")
    print(f"Open: http://127.0.0.1:{port}/?token={app.token}")
    print("Press Ctrl+C to stop. Ratings are saved after each Save.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0


def cmd_listen_export(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.experiment, args.run)
    results, items = load_run(run_dir)
    out, summary = export_listening(run_dir, items, results, args.export_id)
    print(
        f"{summary['records']} record(s) from {summary['reviewers']} reviewer(s); "
        f"excluded {summary['excluded'] or 'none'}"
    )
    print(f"export: {out}")
    return 0


def cmd_audio_inspect(args: argparse.Namespace) -> int:
    try:
        info = inspect_wav(args.wav)
    except AudioCheckError as exc:
        print(f"invalid WAV: {exc}", file=sys.stderr)
        return 1
    check = check_segment_audio(args.wav)
    data = {
        "status": check.status.value,
        "format": {1: "pcm", 3: "float"}.get(info.format_tag, str(info.format_tag)),
        "sample_rate": info.sample_rate,
        "channels": info.channels,
        "bits_per_sample": info.bits_per_sample,
        "duration_s": round(info.duration_s, 3),
    }
    if args.elapsed is not None:
        data["elapsed_s"] = args.elapsed
        data["real_time_factor"] = (
            round(args.elapsed / info.duration_s, 4) if info.duration_s else None
        )
    _print_json(data)
    return 0 if check.ok else 1


def cmd_verify_result(args: argparse.Namespace) -> int:
    problems = validate_verification_result(load_yaml(args.result))
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    print(f"{len(problems)} problem(s)", file=sys.stderr)
    return 1 if problems else 0


def cmd_manifest_validate(args: argparse.Namespace) -> int:
    report = load_manifest(args.manifest)
    print(f"{len(report.entries)} valid entr{'y' if len(report.entries) == 1 else 'ies'}")
    return _report(report.issues, args.strict)


def cmd_splits_check(args: argparse.Namespace) -> int:
    report = load_manifest(args.manifest)
    issues = list(report.issues)
    if report.entries:
        _print_json(
            {
                "counts": split_counts(report.entries),
                "shares": {k: round(v, 3) for k, v in split_shares(report.entries).items()},
            }
        )
        eval_cfg = load_yaml(Path(args.config_dir) / "eval.yaml")
        threshold = get_value(eval_cfg, "leakage.near_duplicate_threshold", allow_tbd=True)
        issues += check_leakage(report.entries, None if is_tbd(threshold) else float(threshold))
        if args.frozen:
            frozen = json.loads(Path(args.frozen).read_text(encoding="utf-8"))
            issues += check_frozen(report.entries, frozen)
    return _report(issues, args.strict)


def cmd_splits_freeze(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite existing freeze file: {out}", file=sys.stderr)
        return 1
    report = load_manifest(args.manifest)
    if not report.ok:
        return _report(report.issues, strict=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(freeze_splits(report.entries), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"froze {len(report.entries)} entries to {out}")
    return 0


def cmd_text_normalize(args: argparse.Namespace) -> int:
    result = Normalizer().normalize(_read_text(args))
    data = asdict(result)
    data["unexpanded_numbers"] = find_unexpanded_numbers(result.normalized_text)
    _print_json(data)
    return 0


def cmd_text_segment(args: argparse.Namespace) -> int:
    max_chars = args.max_chars
    if max_chars is None:
        eval_cfg = load_yaml(Path(args.config_dir) / "eval.yaml")
        value = get_value(eval_cfg, "segmentation.max_chars", allow_tbd=True)
        max_chars = None if is_tbd(value) else int(value)
    for seg in segment_text(args.id, _read_text(args), max_chars=max_chars):
        print(json.dumps(asdict(seg), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tamil-tts", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config-dir", default="configs", help="default: ./configs")
    groups = parser.add_subparsers(dest="group", required=True)

    config = groups.add_parser("config", help="inspect project configuration")
    config_cmds = config.add_subparsers(dest="command", required=True)
    config_cmds.add_parser("show", help="list values still marked TBD").set_defaults(
        func=cmd_config_show
    )

    env = groups.add_parser("env", help="check local data/model/cache roots")
    env_cmds = env.add_subparsers(dest="command", required=True)
    env_cmds.add_parser("check", help="verify TAM_AUDIO_ROOT etc.").set_defaults(func=cmd_env_check)

    models = groups.add_parser("models", help="TTS model candidates")
    models_cmds = models.add_subparsers(dest="command", required=True)
    models_cmds.add_parser("status", help="availability of each candidate").set_defaults(
        func=cmd_models_status
    )

    experiment = groups.add_parser("experiment", help="run experiments locally")
    experiment_cmds = experiment.add_subparsers(dest="command", required=True)
    run = experiment_cmds.add_parser("run", help="run an experiment (writes outside the repo)")
    run.add_argument("experiment", help="e.g. EXP-001")
    run.add_argument("--smoke", action="store_true", help="smoke subset only (PRD §19)")
    run.add_argument("--mock", action="store_true", help="replace every model with a silent mock")
    run.add_argument("--no-cache", action="store_true", help="always synthesize")
    run.add_argument("--run-id", help="default: UTC timestamp")
    run.add_argument("--manifest", type=Path, help="override config manifest path")
    run.add_argument("--frozen", type=Path, help="override config frozen split record")
    run.add_argument("--experiments-dir", default="experiments")
    run.set_defaults(func=cmd_experiment_run)
    status = experiment_cmds.add_parser("status", help="list runs of an experiment")
    status.add_argument("experiment")
    status.set_defaults(func=cmd_experiment_status)

    listen = groups.add_parser("listen", help="local listening evaluation (PRD §17)")
    listen_cmds = listen.add_subparsers(dest="command", required=True)
    serve = listen_cmds.add_parser("serve", help="start the local listening page")
    serve.add_argument("experiment", help="e.g. EXP-001")
    serve.add_argument(
        "--run", required=True, help="run id under $TAMIL_TTS_OUTPUT_ROOT, or latest"
    )
    serve.add_argument("--reviewer", required=True, help="pseudonymous id like REV-01")
    serve.add_argument("--mode", required=True, choices=["blind", "text"])
    serve.add_argument("--session", help="resume this session id")
    serve.add_argument(
        "--manifest",
        type=Path,
        help="private manifest (required for text mode; blind mode uses "
        "it only to reveal text after rating)",
    )
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_listen_serve)
    exp = listen_cmds.add_parser("export", help="write listener_results.jsonl and a summary")
    exp.add_argument("experiment")
    exp.add_argument("--run", required=True)
    exp.add_argument("--export-id", help="default: UTC timestamp")
    exp.set_defaults(func=cmd_listen_export)

    audio = groups.add_parser("audio", help="inspect local audio files")
    audio_cmds = audio.add_subparsers(dest="command", required=True)
    inspect = audio_cmds.add_parser("inspect", help="WAV format, duration, silence, RTF")
    inspect.add_argument("wav", type=Path)
    inspect.add_argument("--elapsed", type=float, help="synthesis seconds, to compute RTF")
    inspect.set_defaults(func=cmd_audio_inspect)

    verify = groups.add_parser("verify", help="model verification records")
    verify_cmds = verify.add_subparsers(dest="command", required=True)
    result = verify_cmds.add_parser("result", help="check a docs/verification/*.yaml file")
    result.add_argument("result", type=Path)
    result.set_defaults(func=cmd_verify_result)

    manifest = groups.add_parser("manifest", help="TAM manifest tools")
    manifest_cmds = manifest.add_subparsers(dest="command", required=True)
    validate = manifest_cmds.add_parser("validate", help="validate a manifest JSONL file")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--strict", action="store_true", help="fail on warnings too")
    validate.set_defaults(func=cmd_manifest_validate)

    splits = groups.add_parser("splits", help="split validation and freezing")
    split_cmds = splits.add_subparsers(dest="command", required=True)
    check = split_cmds.add_parser("check", help="split shares, leakage and frozen membership")
    check.add_argument("manifest", type=Path)
    check.add_argument("--frozen", type=Path, help="frozen split record to compare against")
    check.add_argument("--strict", action="store_true", help="fail on warnings too")
    check.set_defaults(func=cmd_splits_check)
    freeze = split_cmds.add_parser("freeze", help="write a frozen split record (never overwrites)")
    freeze.add_argument("manifest", type=Path)
    freeze.add_argument("--out", required=True, type=Path)
    freeze.set_defaults(func=cmd_splits_freeze)

    text = groups.add_parser("text", help="Tamil front-end tools")
    text_cmds = text.add_subparsers(dest="command", required=True)
    normalize = text_cmds.add_parser("normalize", help="normalize text and show rule changes")
    segment = text_cmds.add_parser("segment", help="segment text into JSONL segments")
    for sub in (normalize, segment):
        sub.add_argument("text", nargs="?")
        sub.add_argument("--file", type=Path)
    segment.add_argument("--id", default="UTT-001", help="utterance id prefix for segment ids")
    segment.add_argument("--max-chars", type=int, help="override segmentation.max_chars")
    normalize.set_defaults(func=cmd_text_normalize)
    segment.set_defaults(func=cmd_text_segment)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        ConfigError,
        ExperimentError,
        SegmentationError,
        RunLoadError,
        SessionError,
        ExportError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
