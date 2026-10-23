"""`tamil-tts` command-line interface.

Implemented: config, env, manifest, splits and text commands. Experiment, listening and
evaluation commands (PRD §12) arrive with the experiment runner.
"""

from __future__ import annotations

import argparse
import json
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
from tamil_tts.frontend import Normalizer, SegmentationError, segment_text
from tamil_tts.frontend.normalize import find_unexpanded_numbers
from tamil_tts.manifest import Issue, load_manifest
from tamil_tts.splits import check_frozen, check_leakage, freeze_splits, split_counts, split_shares


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
    except (ConfigError, SegmentationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
