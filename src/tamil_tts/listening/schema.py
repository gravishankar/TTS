"""Validation of listener submissions against configs/listening.yaml.

A submission is a JSON object from the listening page:

    {"item": "<system_id>/<segment_id>", "ratings": {"comfort": 4, ...},
     "error_categories": ["PHON-LIQUID"], "problem_word_indices": [2], "notes": "..."}

Rules:
- Only items with real audio can be rated; mock, missing, invalid, silent and failed
  items are rejected.
- Each mode has its own criteria; criteria of the other mode are rejected.
- TBD criteria are rejected: their scale is not defined.
- Error categories come from the PRD §9 taxonomy. Problem words are word positions in
  the segment, never the words themselves.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tamil_tts.config import is_tbd
from tamil_tts.listening.items import AUDIO_KIND_TEXT, ListeningItem
from tamil_tts.manifest import TAXONOMY_TAGS

MODES = ("blind", "text")
REVIEWER_RE = re.compile(r"^REV-\d{2,}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ALLOWED_KEYS = {"item", "ratings", "error_categories", "problem_word_indices", "notes"}


def criteria_for(scales: Mapping[str, Any], mode: str) -> dict[str, dict[str, Any]]:
    return {
        name: spec for name, spec in scales["criteria"].items() if mode in spec.get("modes", [])
    }


def public_criteria(scales: Mapping[str, Any], mode: str) -> list[dict[str, Any]]:
    """Criteria as sent to the page; TBD criteria are marked so they are not collected."""
    result = []
    for name, spec in criteria_for(scales, mode).items():
        entry = {"name": name, "label": spec["label"], "type": spec["type"]}
        if is_tbd(spec["type"]):
            entry["type"] = "TBD"
        elif spec["type"] == "choice":
            entry["options"] = [str(o) for o in spec["options"]]
        elif spec["type"] == "scale":
            entry["min"], entry["max"] = int(spec["min"]), int(spec["max"])
        entry["required"] = bool(spec.get("required")) and not is_tbd(spec["type"])
        result.append(entry)
    return result


def word_count(text: str) -> int:
    return len(text.split())


def validate_submission(
    payload: Any, item: ListeningItem | None, mode: str, scales: Mapping[str, Any]
) -> list[str]:
    """Return problems; an empty list means the submission can be saved."""
    if not isinstance(payload, Mapping):
        return ["submission must be a JSON object"]
    if item is None:
        return ["unknown item"]
    if not item.rateable:
        return [f"cannot rate this item: {AUDIO_KIND_TEXT[item.audio_kind]}"]
    problems = [f"unexpected field '{k}'" for k in sorted(set(payload) - ALLOWED_KEYS)]

    ratings = payload.get("ratings")
    if not isinstance(ratings, Mapping):
        return problems + ["ratings must be an object"]
    allowed = criteria_for(scales, mode)
    for name in sorted(set(ratings) - set(allowed)):
        problems.append(f"'{name}' is not collected in {mode} mode")
    for name, spec in allowed.items():
        value = ratings.get(name)
        if is_tbd(spec["type"]):
            if value is not None:
                problems.append(f"'{name}' has no defined scale (TBD); it cannot be recorded")
            continue
        if value is None:
            if spec.get("required"):
                problems.append(f"'{name}' is required")
            continue
        if spec["type"] == "choice" and value not in [str(o) for o in spec["options"]]:
            problems.append(f"'{name}' must be one of {spec['options']}")
        if spec["type"] == "scale" and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not spec["min"] <= value <= spec["max"]
        ):
            problems.append(f"'{name}' must be an integer from {spec['min']} to {spec['max']}")

    categories = payload.get("error_categories", [])
    indices = payload.get("problem_word_indices", [])
    if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
        problems.append("error_categories must be a list of taxonomy tags")
        categories = []
    if not isinstance(indices, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in indices
    ):
        problems.append("problem_word_indices must be a list of integers")
        indices = []
    unknown = sorted(set(categories) - TAXONOMY_TAGS)
    if unknown:
        problems.append(f"unknown error categories: {', '.join(unknown)}")
    if len(set(categories)) != len(categories) or len(set(indices)) != len(indices):
        problems.append("error_categories and problem_word_indices must not repeat")

    if mode == "blind":
        if indices:
            problems.append("problem words need visible text; use text mode")
    else:
        if item.text is None:
            problems.append("reference text is not available for this item")
        elif indices and not all(0 <= i < word_count(item.text) for i in indices):
            problems.append("problem_word_indices out of range")
        if ratings.get("pronunciation") == "errors" and not categories:
            problems.append("choose at least one error category when pronunciation has errors")

    notes = payload.get("notes", "")
    max_chars = int(scales.get("notes", {}).get("max_chars", 1000))
    if not isinstance(notes, str) or len(notes) > max_chars:
        problems.append(f"notes must be text of at most {max_chars} characters")
    return problems
