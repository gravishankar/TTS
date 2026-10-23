"""Validate local model-verification result files (docs/verification/*.yaml).

The template is docs/verification/TEMPLATE.yaml. A result may be marked VERIFIED only
when the source, licence, pinned revision, interface and at least one listened-to smoke
test are all recorded. Result files are committed, so they must not contain absolute
paths or private data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

STATUSES = frozenset({"VERIFIED", "UNVERIFIED", "FAILED"})
SMOKE_STATUSES = frozenset({"PASS", "FAIL", "UNVERIFIED"})
REQUIRED_SECTIONS = (
    "model",
    "date",
    "overall_status",
    "source",
    "license",
    "environment",
    "interface",
    "smoke_tests",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRIVATE_PATH = re.compile(r"(/Users/|/home/|/private/|/var/folders/|[A-Za-z]:\\\\)")


def _walk_strings(value: Any, prefix: str = ""):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_strings(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def validate_verification_result(data: Any) -> list[str]:
    """Return a list of problems; an empty list means the file is consistent."""
    if not isinstance(data, Mapping):
        return ["result must be a mapping"]
    problems = [f"missing section '{key}'" for key in REQUIRED_SECTIONS if key not in data]
    if problems:
        return problems

    for where, text in _walk_strings(data):
        if _PRIVATE_PATH.search(text):
            problems.append(f"{where}: contains an absolute path; use a path relative to $HOME")

    status = data["overall_status"]
    if status not in STATUSES:
        problems.append(f"overall_status must be one of {sorted(STATUSES)}")
    if not DATE_RE.match(str(data["date"])):
        problems.append("date must be YYYY-MM-DD")

    smoke_tests = data["smoke_tests"]
    if not isinstance(smoke_tests, list):
        return problems + ["smoke_tests must be a list"]
    for index, test in enumerate(smoke_tests):
        if not isinstance(test, Mapping) or test.get("status") not in SMOKE_STATUSES:
            problems.append(f"smoke_tests[{index}].status must be one of {sorted(SMOKE_STATUSES)}")

    if status == "VERIFIED":
        source, licence, interface = data["source"], data["license"], data["interface"]
        if not SHA_RE.match(str(source.get("weights_revision", ""))):
            problems.append("VERIFIED needs source.weights_revision as a full 40-character SHA")
        if not str(licence.get("weights") or "").strip():
            problems.append("VERIFIED needs license.weights")
        if licence.get("permits_evaluation") is not True:
            problems.append("VERIFIED needs license.permits_evaluation: true")
        if interface.get("status") != "VERIFIED" or not str(interface.get("invocation") or ""):
            problems.append("VERIFIED needs interface.status VERIFIED and interface.invocation")
        listened = [
            t
            for t in smoke_tests
            if isinstance(t, Mapping)
            and t.get("status") == "PASS"
            and (t.get("listening") or {}).get("all_words_spoken") is True
        ]
        if not listened:
            problems.append("VERIFIED needs a PASS smoke test with listening.all_words_spoken")
    if status == "FAILED" and not str(data.get("stop_reason") or "").strip():
        problems.append("FAILED needs stop_reason")
    return problems
