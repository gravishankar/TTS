"""TAM manifest schema and validator (PRD §7, §8, §9).

One JSON object per line:

    {"id":"TAM-001","split":"train","text":"<Tamil>","audio":"${TAM_AUDIO_ROOT}/TAM-001.wav",
     "speaker_id":"SPK-01","tags":["literary","PHON-LIQUID"],"quality":"accepted"}

Optional field `permissions` lists what the recording may be used for ("training",
"distribution"). Training and distribution are refused without it (C2 decision 10).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPLITS = ("train", "validate", "test", "challenge")
PROTECTED_SPLITS = frozenset({"test", "challenge"})
TAXONOMY_TAGS = frozenset(
    {
        "PHON-LIQUID",
        "PHON-RHOTIC",
        "PHON-NASAL",
        "PHON-VOWEL",
        "PHON-GEM",
        "SCRIPT-GRANTHA",
        "PROSODY",
        "NORM-NUM",
        "MIXED",
        "LITERARY",
        "ACCESS",
    }
)
PERMISSIONS = frozenset({"training", "distribution"})
KNOWN_QUALITY = frozenset({"accepted"})

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "split": str,
    "text": str,
    "audio": str,
    "speaker_id": str,
    "tags": list,
    "quality": str,
}
OPTIONAL_FIELDS: dict[str, type] = {"permissions": list}

ID_RE = re.compile(r"^TAM-\d{3,}$")
# Pseudonymous speaker codes only: no names or other identifying information.
SPEAKER_RE = re.compile(r"^SPK-\d{2,}$")
AUDIO_PREFIX = "${TAM_AUDIO_ROOT}/"
AUDIO_SUFFIX = ".wav"


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" or "warning"
    message: str
    line: int | None = None
    entry_id: str | None = None

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line is not None else "manifest"
        who = f" [{self.entry_id}]" if self.entry_id else ""
        return f"{self.severity.upper()}: {where}{who}: {self.message}"


@dataclass(frozen=True)
class ManifestEntry:
    id: str
    split: str
    text: str
    audio: str
    speaker_id: str
    tags: tuple[str, ...]
    quality: str
    permissions: tuple[str, ...] = ()
    line: int | None = None


@dataclass
class ManifestReport:
    entries: list[ManifestEntry] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_record(
    record: Any, line: int | None = None
) -> tuple[ManifestEntry | None, list[Issue]]:
    """Validate one decoded manifest record."""
    if not isinstance(record, dict):
        return None, [Issue("error", "record must be a JSON object", line)]
    entry_id = record.get("id") if isinstance(record.get("id"), str) else None
    issues: list[Issue] = []

    def err(msg: str) -> None:
        issues.append(Issue("error", msg, line, entry_id))

    def warn(msg: str) -> None:
        issues.append(Issue("warning", msg, line, entry_id))

    for name, kind in REQUIRED_FIELDS.items():
        if name not in record:
            err(f"missing required field '{name}'")
        elif not isinstance(record[name], kind):
            err(f"field '{name}' must be {kind.__name__}")
    for name, kind in OPTIONAL_FIELDS.items():
        if name in record and not isinstance(record[name], kind):
            err(f"field '{name}' must be {kind.__name__}")
    for name in sorted(set(record) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)):
        warn(f"unknown field '{name}'; make sure it holds no identifying information")
    if issues and any(i.severity == "error" for i in issues):
        return None, issues

    if not ID_RE.match(record["id"]):
        err("id must look like TAM-001")
    if record["split"] not in SPLITS:
        err(f"split must be one of {', '.join(SPLITS)}")
    if not record["text"].strip():
        err("text is empty")

    audio = record["audio"]
    if not audio.startswith(AUDIO_PREFIX):
        err(f"audio must start with {AUDIO_PREFIX} (no personal or absolute paths)")
    elif ".." in Path(audio[len(AUDIO_PREFIX) :]).parts:
        err("audio path must not contain '..'")
    if not audio.lower().endswith(AUDIO_SUFFIX):
        err("audio must be a .wav file")

    if not SPEAKER_RE.match(record["speaker_id"]):
        err("speaker_id must be a pseudonymous code like SPK-01")

    tags = record["tags"]
    if not all(isinstance(t, str) for t in tags):
        err("tags must be strings")
    else:
        for tag in tags:
            if tag.upper() not in TAXONOMY_TAGS:
                warn(f"tag '{tag}' is not in the PRD §9 taxonomy")

    if record["quality"] not in KNOWN_QUALITY:
        warn(f"quality '{record['quality']}' is not a known value ({', '.join(KNOWN_QUALITY)})")

    permissions = record.get("permissions", [])
    if not all(isinstance(p, str) and p in PERMISSIONS for p in permissions):
        err(f"permissions may only contain {', '.join(sorted(PERMISSIONS))}")

    if any(i.severity == "error" for i in issues):
        return None, issues
    entry = ManifestEntry(
        id=record["id"],
        split=record["split"],
        text=record["text"],
        audio=audio,
        speaker_id=record["speaker_id"],
        tags=tuple(tags),
        quality=record["quality"],
        permissions=tuple(permissions),
        line=line,
    )
    return entry, issues


def validate_lines(lines: list[str]) -> ManifestReport:
    report = ManifestReport()
    seen: dict[str, int | None] = {}
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            report.issues.append(Issue("error", f"invalid JSON: {exc.msg}", number))
            continue
        entry, issues = validate_record(record, number)
        report.issues.extend(issues)
        if entry is None:
            continue
        if entry.id in seen:
            report.issues.append(
                Issue("error", f"duplicate id (first on line {seen[entry.id]})", number, entry.id)
            )
            continue
        seen[entry.id] = number
        report.entries.append(entry)
    if not report.entries and not report.issues:
        report.issues.append(Issue("error", "manifest has no entries"))
    return report


def load_manifest(path: Path) -> ManifestReport:
    path = Path(path)
    if not path.is_file():
        return ManifestReport(issues=[Issue("error", f"manifest not found: {path}")])
    return validate_lines(path.read_text(encoding="utf-8").splitlines())
