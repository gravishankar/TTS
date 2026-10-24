"""Export listener results and a privacy-safe summary (PRD §15, §17).

Each export goes to a new directory `<run>/listening/exports/<export_id>/`:

- listener_results.jsonl  one record per (session, item): pseudonymous reviewer id, ratings,
                          categories, word positions. No notes, no text, no paths.
- listening_summary.json  aggregate counts per system; automatic checks kept separate.
- LISTENING_REPORT.md     the same summary for people.

Records are re-checked on export: only real audio counts, and a rating whose audio
changed since it was given (different sha256) is excluded as stale.
"""

from __future__ import annotations

import json
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
    "submitted_at",
)


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


def summarize(
    records: list[dict[str, Any]], excluded: Mapping[str, int], results: Mapping[str, Any]
) -> dict[str, Any]:
    systems: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ratings": defaultdict(Counter), "comfort": [], "categories": Counter()}
    )
    for record in records:
        data = systems[record["system_id"]]
        for name, value in record["ratings"].items():
            if name == "comfort":
                data["comfort"].append(value)
            else:
                data["ratings"][f"{record['mode']}.{name}"][str(value)] += 1
        data["categories"].update(record["error_categories"])

    human = {}
    for system_id, data in sorted(systems.items()):
        comfort = data["comfort"]
        human[system_id] = {
            "judgments": {k: dict(sorted(v.items())) for k, v in sorted(data["ratings"].items())},
            "comfort": {
                "n": len(comfort),
                "median": statistics.median(comfort) if comfort else None,
                "distribution": dict(sorted(Counter(comfort).items())),
            },
            "error_categories": dict(sorted(data["categories"].items())),
        }

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
        "human_judgments": human,
        "targets": {
            "comfort": "PRD provisional target: median >= 4/5 and not below baseline. "
            "Not evaluated: no baseline yet.",
            "challenge_intelligibility": "PRD provisional target: >= 90%. Not evaluated: "
            "scoring unit is TBD.",
            "completeness": "Human 'all words spoken' judgments are reported, not gated.",
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
        "Audio present and not silent. These checks cannot hear missing words or mispronunciation.",
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
    lines += ["", "## Human judgments (listeners)", ""]
    if not summary["human_judgments"]:
        lines.append("No ratings yet.")
    for system_id, h in summary["human_judgments"].items():
        lines += [f"### {system_id}", ""]
        for name, counts in h["judgments"].items():
            lines.append(f"- {name}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        c = h["comfort"]
        lines.append(
            f"- comfort: n {c['n']}, median {c['median']}, distribution {c['distribution']}"
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
