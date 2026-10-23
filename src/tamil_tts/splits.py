"""Split validation, leakage checks, frozen-split guard and training guard (PRD §8, §18).

- TEST and CHALLENGE never participate in training.
- Split membership is frozen after EXP-001: frozen ids may not move or disappear, and
  new ids may not enter TEST/CHALLENGE (new failures go to a versioned future set).
- Training and distribution require recording permission on every entry used.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

from tamil_tts.manifest import PROTECTED_SPLITS, SPLITS, Issue, ManifestEntry

FREEZE_FORMAT_VERSION = 1
TARGET_SHARES = {"train": 0.70, "validate": 0.10, "test": 0.10, "challenge": 0.10}


class SplitGuardError(Exception):
    """An operation would use protected data or data without permission."""


def split_counts(entries: Iterable[ManifestEntry]) -> dict[str, int]:
    counts = Counter(e.split for e in entries)
    return {split: counts.get(split, 0) for split in SPLITS}


def split_shares(entries: Iterable[ManifestEntry]) -> dict[str, float]:
    counts = split_counts(entries)
    total = sum(counts.values())
    return {split: (n / total if total else 0.0) for split, n in counts.items()}


def _comparison_key(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def check_leakage(
    entries: list[ManifestEntry], near_duplicate_threshold: float | None = None
) -> list[Issue]:
    """Report text and speaker leakage between splits.

    `near_duplicate_threshold` is a SequenceMatcher ratio in (0, 1]. It is TBD in the
    PRD, so when it is None the near-duplicate check is skipped with a warning.
    """
    issues: list[Issue] = []

    by_text: dict[str, list[ManifestEntry]] = defaultdict(list)
    for entry in entries:
        by_text[_comparison_key(entry.text)].append(entry)
    for group in by_text.values():
        splits = sorted({e.split for e in group})
        if len(splits) > 1:
            ids = ", ".join(e.id for e in group)
            issues.append(Issue("error", f"identical text across splits {splits}: {ids}"))

    trainable = [e for e in entries if e.split not in PROTECTED_SPLITS]
    protected = [e for e in entries if e.split in PROTECTED_SPLITS]

    train_speakers = {e.speaker_id for e in trainable if e.split == "train"}
    shared = sorted(train_speakers & {e.speaker_id for e in protected})
    if shared:
        issues.append(
            Issue(
                "warning",
                f"speakers in both TRAIN and TEST/CHALLENGE: {', '.join(shared)} "
                "(split by speaker where feasible)",
            )
        )

    if near_duplicate_threshold is None:
        issues.append(Issue("warning", "near-duplicate check skipped: threshold is TBD"))
    else:
        if not 0 < near_duplicate_threshold <= 1:
            raise ValueError("near_duplicate_threshold must be in (0, 1]")
        for p in protected:
            p_key = _comparison_key(p.text)
            for t in trainable:
                t_key = _comparison_key(t.text)
                if t_key == p_key:
                    continue  # already reported as identical
                ratio = SequenceMatcher(None, p_key, t_key).ratio()
                if ratio >= near_duplicate_threshold:
                    issues.append(
                        Issue(
                            "error",
                            f"near-duplicate text ({ratio:.2f}) between {t.id} ({t.split}) "
                            f"and {p.id} ({p.split})",
                        )
                    )
    return issues


def freeze_splits(entries: Iterable[ManifestEntry]) -> dict[str, Any]:
    """Return a commit-safe record of split membership (ids and splits only, no text)."""
    membership = {e.id: e.split for e in sorted(entries, key=lambda e: e.id)}
    return {
        "format_version": FREEZE_FORMAT_VERSION,
        "membership": membership,
        "checksum": _membership_checksum(membership),
    }


def _membership_checksum(membership: dict[str, str]) -> str:
    canonical = json.dumps(membership, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_frozen(entries: list[ManifestEntry], frozen: dict[str, Any]) -> list[Issue]:
    """Compare current split membership with a frozen record."""
    if frozen.get("format_version") != FREEZE_FORMAT_VERSION:
        return [Issue("error", "unsupported frozen split format")]
    membership = frozen.get("membership")
    if not isinstance(membership, dict):
        return [Issue("error", "frozen split record has no membership")]
    if frozen.get("checksum") != _membership_checksum(membership):
        return [Issue("error", "frozen split record checksum does not match; it was edited")]

    issues: list[Issue] = []
    current = {e.id: e.split for e in entries}
    for entry_id, split in sorted(membership.items()):
        if entry_id not in current:
            issues.append(Issue("error", f"frozen entry removed (was {split})", entry_id=entry_id))
        elif current[entry_id] != split:
            issues.append(
                Issue(
                    "error",
                    f"frozen split changed: {split} -> {current[entry_id]}",
                    entry_id=entry_id,
                )
            )
    for entry_id, split in sorted(current.items()):
        if entry_id not in membership and split in PROTECTED_SPLITS:
            issues.append(
                Issue(
                    "error",
                    f"new entry added to frozen {split}; use a versioned future challenge set",
                    entry_id=entry_id,
                )
            )
    return issues


def require_permission(entries: Iterable[ManifestEntry], permission: str) -> None:
    missing = sorted(e.id for e in entries if permission not in e.permissions)
    if missing:
        raise SplitGuardError(f"no '{permission}' permission recorded for: {', '.join(missing)}")


def training_entries(entries: Iterable[ManifestEntry]) -> list[ManifestEntry]:
    """Entries allowed to supply gradient updates: TRAIN only, with training permission."""
    train = [e for e in entries if e.split == "train"]
    require_permission(train, "training")
    return train


def assert_no_protected(entries: Iterable[ManifestEntry]) -> None:
    """Raise if any TEST/CHALLENGE entry is about to be used for training or selection."""
    leaked = sorted(e.id for e in entries if e.split in PROTECTED_SPLITS)
    if leaked:
        raise SplitGuardError(f"TEST/CHALLENGE entries may not be used here: {', '.join(leaked)}")
