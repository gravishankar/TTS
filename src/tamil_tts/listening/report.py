"""Export listener results and a privacy-safe summary (PRD §15, §17).

Each export goes to a new directory `<run>/listening/exports/<export_id>/`:

- listener_results.jsonl  one record per (session, item): pseudonymous reviewer id, ratings,
                          categories, word positions. No notes, no text, no paths.
- listening_summary.json  aggregate counts per system; automatic checks kept separate.
- LISTENING_REPORT.md     the same summary for people.

Records are re-checked on export: only real audio counts, and a rating whose audio
changed since it was given (different sha256) is excluded as stale.

Git policy (C5A): individual listener records, session files, reviewer notes, private
Tamil text and audio never enter Git. Only a reviewed, anonymized aggregate
(listening_summary.json + LISTENING_REPORT.md) may be copied into the repository, with
`publish`, which runs `check_public` first.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tamil_tts.listening.items import ListeningItem
from tamil_tts.listening.schema import SESSION_RE
from tamil_tts.listening.store import all_sessions

EXPORT_FIELDS = (
    "format_version",
    "reviewer_id",
    "session_id",
    "mode",
    "experiment",
    "run_id",
    "system_id",
    "segment_id",
    "id",
    "split",
    "tags",
    "segment_sha256",
    "audio_sha256",
    "ratings",
    "error_categories",
    "problem_word_indices",
    "order_seed",
    "presentation_position",
    "revision",
    "submitted_at",
)
MODE_TITLES = {
    "blind": "Blind listening (model identity and text hidden while rating)",
    "text": "Text-assisted verification (Tamil reference text visible)",
}
INTERPRETATION = {
    "perceived_intelligibility": "Blind perceived intelligibility is NOT evidence that every "
    "word was spoken. Only text-assisted completeness judgments address missing words. "
    "Intelligibility is judged per segment.",
    "scales": "Naturalness (1-5) and error severity (0-3) are project-specific scales. They are "
    "not externally validated MOS measurements and must not be compared with published MOS.",
    "automatic_checks": "Automatic checks only show that audio exists and is not silent. They "
    "are machine checks, reported separately from human judgments.",
}


class ExportError(Exception):
    """The export cannot be written."""


def collect(
    run_dir: Path, items: Mapping[str, ListeningItem]
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Latest record per (session, item), filtered for real and unchanged audio."""
    kept: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for session in all_sessions(run_dir):
        for key, record in sorted(session.latest().items()):
            item = items.get(key)
            if record.get("audio_kind") != "real" or item is None or not item.rateable:
                excluded["not_real_audio"] += 1
            elif record.get("audio_sha256") != item.audio_sha256:
                excluded["stale_audio_changed"] += 1
            else:
                kept.append({field: record.get(field) for field in EXPORT_FIELDS})
    return kept, excluded


NUMERIC_SCALES = ("comfort", "naturalness", "error_severity")


def _human(records: list[dict[str, Any]]) -> dict[str, Any]:
    systems: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "ratings": defaultdict(Counter),
            "numeric": defaultdict(list),
            "categories": Counter(),
        }
    )
    for record in records:
        data = systems[record["system_id"]]
        for name, value in record["ratings"].items():
            if name in NUMERIC_SCALES:
                data["numeric"][name].append(value)
            else:
                data["ratings"][name][str(value)] += 1
        data["categories"].update(record["error_categories"])
    human = {}
    for system_id, data in sorted(systems.items()):
        entry: dict[str, Any] = {
            "judgments": {k: dict(sorted(v.items())) for k, v in sorted(data["ratings"].items())},
            "error_categories": dict(sorted(data["categories"].items())),
        }
        for name in NUMERIC_SCALES:
            values = data["numeric"].get(name)
            if values:
                entry[name] = {
                    "n": len(values),
                    "median": statistics.median(values),
                    "distribution": {str(k): v for k, v in sorted(Counter(values).items())},
                }
        human[system_id] = entry
    return human


def summarize(
    records: list[dict[str, Any]], excluded: Mapping[str, int], results: Mapping[str, Any]
) -> dict[str, Any]:
    automatic = {
        s["system_id"]: {
            "ran": s.get("ran"),
            "segments_total": s.get("segments_total"),
            "segments_ok": s.get("segments_ok"),
            "segments_silent": s.get("segments_silent"),
            "segments_error": s.get("segments_error"),
            "gate_completeness": s.get("gate_completeness"),
        }
        for s in results.get("systems", [])
    }
    return {
        "experiment": results.get("experiment"),
        "run_id": results.get("run_id"),
        "mock_run": bool(results.get("mock")),
        "reviewers": len({r["reviewer_id"] for r in records}),
        "records": len(records),
        "excluded": dict(excluded),
        "automatic_checks": automatic,
        "human_judgments": {
            mode: _human([r for r in records if r["mode"] == mode]) for mode in MODE_TITLES
        },
        "interpretation": INTERPRETATION,
        "review": {"status": "unreviewed", "reviewed_by": None, "reviewed_on": None},
        "targets": {
            "comfort": "PRD provisional target: median >= 4/5 and not below baseline. "
            "Not evaluated: no baseline yet.",
            "challenge_intelligibility": "PRD provisional target: >= 90%. Not evaluated: "
            "scoring unit is TBD.",
            "completeness": "Text-assisted 'all words spoken' judgments are reported, not gated.",
            "naturalness": "Project-specific 1-5 scale; no target defined.",
            "error_severity": "Project-specific 0-3 scale; no target defined.",
        },
    }


def render(summary: Mapping[str, Any]) -> str:
    lines = [f"# Listening summary — {summary['experiment']} run {summary['run_id']}", ""]
    if summary["mock_run"]:
        lines += ["> **MOCK RUN.** No audio in this run can be rated; it is not speech.", ""]
    lines += [
        f"- Reviewers: {summary['reviewers']} (pseudonymous) · Records: {summary['records']}",
        "- Excluded: " + (", ".join(f"{k} {v}" for k, v in summary["excluded"].items()) or "none"),
        "",
        "## Automatic checks (machine)",
        "",
        "| System | Ran | OK / total | Silent | Errors | Completeness gate |",
        "|---|---|---|---|---|---|",
    ]
    for system_id, a in summary["automatic_checks"].items():
        lines.append(
            f"| {system_id} | {a['ran']} | {a['segments_ok']} / {a['segments_total']} | "
            f"{a['segments_silent'] if a['segments_silent'] is not None else '–'} | "
            f"{a['segments_error'] if a['segments_error'] is not None else '–'} | "
            f"{a['gate_completeness']} |"
        )
    lines += ["", f"_{summary['interpretation']['automatic_checks']}_"]
    lines += ["", f"_{summary['interpretation']['scales']}_"]
    for mode, title in MODE_TITLES.items():
        lines += ["", f"## Human judgments — {title}", ""]
        if mode == "blind":
            lines += [f"_{summary['interpretation']['perceived_intelligibility']}_", ""]
        judged = summary["human_judgments"][mode]
        if not judged:
            lines += ["No ratings yet.", ""]
        for system_id, h in judged.items():
            lines += [f"### {system_id}", ""]
            for name, counts in h["judgments"].items():
                lines.append(f"- {name}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
            for name in NUMERIC_SCALES:
                if name in h:
                    c = h[name]
                    lines.append(
                        f"- {name}: n {c['n']}, median {c['median']}, "
                        f"distribution {c['distribution']}"
                    )
            if h["error_categories"]:
                lines.append(
                    "- error categories: "
                    + ", ".join(f"{k} {v}" for k, v in h["error_categories"].items())
                )
            lines.append("")
    lines += ["## Targets", ""]
    lines += [f"- **{k}**: {v}" for k, v in summary["targets"].items()]
    lines += [
        "",
        "---",
        "Generated by `tamil-tts listen export`. Contains ids, counts and pseudonymous reviewer",
        "codes only; no Tamil text, notes, audio or paths.",
        "",
    ]
    return "\n".join(lines)


def export(
    run_dir: Path,
    items: list[ListeningItem],
    results: Mapping[str, Any],
    export_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    export_id = export_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not SESSION_RE.match(export_id):
        raise ExportError("invalid export id")
    base = Path(run_dir) / "listening" / "exports"
    base.mkdir(parents=True, exist_ok=True)
    out = base / export_id
    try:
        out.mkdir()
    except FileExistsError as exc:
        raise ExportError(f"export already exists, not overwriting: {export_id}") from exc

    records, excluded = collect(run_dir, {i.key: i for i in items})
    summary = summarize(records, excluded, results)
    with (out / "listener_results.jsonl").open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    with (out / "listening_summary.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with (out / "LISTENING_REPORT.md").open("x", encoding="utf-8") as handle:
        handle.write(render(summary))
    return out, summary


PUBLIC_FILES = ("listening_summary.json", "LISTENING_REPORT.md")
# Per-record or private fields. ("text" is not listed: it is also the text-assisted mode
# key; actual Tamil text is caught by the script check below.)
FORBIDDEN_KEYS = frozenset(
    {"notes", "reviewer_id", "session_id", "problem_word_indices", "audio", "audio_path"}
)
_ABS_PATH = re.compile(r"(/Users/|/home/|/private/|/var/folders/|[A-Za-z]:\\\\)")
_REVIEWER = re.compile(r"^REV-\d{2,}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        found = set(value)
        for item in value.values():
            found |= _keys(item)
        return found
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


def check_public(directory: Path) -> list[str]:
    """Problems that stop an aggregate listening report from entering Git."""
    directory = Path(directory)
    problems = []
    names = {p.name for p in directory.iterdir()} if directory.is_dir() else set()
    missing = [n for n in PUBLIC_FILES if n not in names]
    if missing:
        return [f"missing {', '.join(missing)}"]
    extra = sorted(names - set(PUBLIC_FILES))
    if extra:
        problems.append(f"only aggregate files may be published; remove {', '.join(extra)}")
    summary = json.loads((directory / "listening_summary.json").read_text(encoding="utf-8"))
    review = summary.get("review") or {}
    if review.get("status") != "reviewed":
        problems.append("review.status must be 'reviewed'")
    if not _REVIEWER.match(str(review.get("reviewed_by") or "")):
        problems.append("review.reviewed_by must be a pseudonymous code like REV-01")
    if not _DATE.match(str(review.get("reviewed_on") or "")):
        problems.append("review.reviewed_on must be YYYY-MM-DD")
    leaked = sorted(_keys(summary) & FORBIDDEN_KEYS)
    if leaked:
        problems.append(f"summary holds individual or private fields: {', '.join(leaked)}")
    for name in PUBLIC_FILES:
        content = (directory / name).read_text(encoding="utf-8")
        if any("\u0b80" <= c <= "\u0bff" for c in content):
            problems.append(f"{name} contains Tamil text")
        if _ABS_PATH.search(content):
            problems.append(f"{name} contains an absolute path")
    return problems


def publish(
    export_dir: Path, destination_root: Path, *, reviewed_by: str, reviewed_on: str
) -> Path:
    """Copy a reviewed aggregate into the repository. Never copies individual records."""
    export_dir = Path(export_dir)
    out = Path(destination_root) / export_dir.name
    if out.exists():
        raise ExportError(f"already published, not overwriting: {out}")
    summary = json.loads((export_dir / "listening_summary.json").read_text(encoding="utf-8"))
    summary["review"] = {
        "status": "reviewed",
        "reviewed_by": reviewed_by,
        "reviewed_on": reviewed_on,
    }
    staging = out.with_name(out.name + ".partial")
    if staging.exists():
        raise ExportError(f"leftover staging folder, remove it first: {staging}")
    staging.mkdir(parents=True)
    (staging / "listening_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (staging / "LISTENING_REPORT.md").write_text(
        render(summary) + f"\nReviewed by {reviewed_by} on {reviewed_on} before publication.\n",
        encoding="utf-8",
    )
    problems = check_public(staging)
    if problems:
        for child in staging.iterdir():
            child.unlink()
        staging.rmdir()
        raise ExportError("not publishable: " + "; ".join(problems))
    staging.rename(out)
    return out
