"""Listening sessions: create, resume, append ratings, export.

Layout inside the run directory (outside Git, under $TAMIL_TTS_OUTPUT_ROOT):

    <run>/listening/sessions/<session_id>/session.json   # reviewer, mode, order seed
    <run>/listening/sessions/<session_id>/ratings.jsonl  # append-only; latest per item wins
    <run>/listening/exports/<export_id>/                 # listener_results.jsonl + summary

Session files are private: they may hold reviewer notes. Nothing is ever rewritten: a
changed rating is a new line, and every export goes to a new directory.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tamil_tts.listening.items import ListeningItem
from tamil_tts.listening.schema import MODES, REVIEWER_RE, SESSION_RE

RECORD_FORMAT_VERSION = 1


class SessionError(Exception):
    """A session cannot be created, resumed or written."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Session:
    directory: Path
    meta: dict[str, Any]

    @property
    def session_id(self) -> str:
        return self.meta["session_id"]

    @property
    def mode(self) -> str:
        return self.meta["mode"]

    @property
    def reviewer_id(self) -> str:
        return self.meta["reviewer_id"]

    @property
    def ratings_path(self) -> Path:
        return self.directory / "ratings.jsonl"

    def records(self) -> list[dict[str, Any]]:
        if not self.ratings_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.ratings_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def latest(self) -> dict[str, dict[str, Any]]:
        """Latest record per item key."""
        latest: dict[str, dict[str, Any]] = {}
        for record in self.records():
            latest[record["item"]] = record
        return latest

    def append(self, item: ListeningItem, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Append a validated submission. The caller validates first."""
        record = {
            "format_version": RECORD_FORMAT_VERSION,
            "session_id": self.session_id,
            "reviewer_id": self.reviewer_id,
            "mode": self.mode,
            "experiment": self.meta["experiment"],
            "run_id": self.meta["run_id"],
            "item": item.key,
            "system_id": item.system_id,
            "segment_id": item.segment_id,
            "id": item.entry_id,
            "split": item.split,
            "tags": list(item.tags),
            "segment_sha256": item.segment_sha256,
            "audio_kind": item.audio_kind.value,
            "audio_sha256": item.audio_sha256,
            "ratings": dict(payload.get("ratings", {})),
            "error_categories": list(payload.get("error_categories", [])),
            "problem_word_indices": list(payload.get("problem_word_indices", [])),
            "notes": str(payload.get("notes", "")),
            "seq": len(self.records()) + 1,
            "submitted_at": _now(),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self.ratings_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return record


def sessions_dir(run_dir: Path) -> Path:
    return Path(run_dir) / "listening" / "sessions"


def open_session(
    run_dir: Path,
    *,
    experiment: str,
    run_id: str,
    reviewer_id: str,
    mode: str,
    session_id: str | None = None,
) -> tuple[Session, bool]:
    """Create a new session, or resume `session_id`. Returns (session, resumed)."""
    if not REVIEWER_RE.match(reviewer_id):
        raise SessionError("reviewer id must be a pseudonymous code like REV-01 (no names)")
    if mode not in MODES:
        raise SessionError(f"mode must be one of {', '.join(MODES)}")
    if session_id is not None and not SESSION_RE.match(session_id):
        raise SessionError("invalid session id")

    base = sessions_dir(run_dir)
    if session_id is not None and (base / session_id / "session.json").is_file():
        directory = base / session_id
        meta = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        if meta["reviewer_id"] != reviewer_id or meta["mode"] != mode:
            raise SessionError(
                f"session {session_id} belongs to {meta['reviewer_id']} in {meta['mode']} mode"
            )
        return Session(directory, meta), True

    created = datetime.now(UTC)
    session_id = session_id or f"{reviewer_id}-{mode}-{created.strftime('%Y%m%dT%H%M%SZ')}"
    directory = base / session_id
    base.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise SessionError(f"session directory exists but is incomplete: {session_id}") from exc
    meta = {
        "format_version": RECORD_FORMAT_VERSION,
        "session_id": session_id,
        "reviewer_id": reviewer_id,
        "mode": mode,
        "experiment": experiment,
        "run_id": run_id,
        "order_seed": session_id,
        "created_at": created.isoformat(timespec="seconds"),
    }
    with (directory / "session.json").open("x", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, sort_keys=True)
    return Session(directory, meta), False


def all_sessions(run_dir: Path) -> list[Session]:
    base = sessions_dir(run_dir)
    if not base.is_dir():
        return []
    sessions = []
    for directory in sorted(p for p in base.iterdir() if (p / "session.json").is_file()):
        meta = json.loads((directory / "session.json").read_text(encoding="utf-8"))
        sessions.append(Session(directory, meta))
    return sessions
