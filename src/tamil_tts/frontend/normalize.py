"""Deterministic, auditable text normalization (PRD §10).

The source text is never modified; normalization returns a new string plus a record
of every rule that changed it. Only language-neutral rules ship by default. Tamil
number, date, currency and unit expansion and lexicon overrides plug in as further
rules once their reading rules are specified; until then `find_unexpanded_numbers`
flags digits so they are not silently mispronounced.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

# ASCII digits and Tamil digits ௦-௯ (U+0BE6..U+0BEF).
_NUMBER_RE = re.compile(r"[0-9௦-௯]+(?:[.,][0-9௦-௯]+)*")


class Rule(Protocol):
    name: str

    def apply(self, text: str) -> str: ...


@dataclass(frozen=True)
class UnicodeNFC:
    name: str = "unicode-nfc"

    def apply(self, text: str) -> str:
        return unicodedata.normalize("NFC", text)


@dataclass(frozen=True)
class RegexRule:
    name: str
    pattern: str
    replacement: str

    def apply(self, text: str) -> str:
        return re.sub(self.pattern, self.replacement, text)


@dataclass(frozen=True)
class Strip:
    name: str = "strip"

    def apply(self, text: str) -> str:
        return text.strip()


DEFAULT_RULES: tuple[Rule, ...] = (
    UnicodeNFC(),
    RegexRule("collapse-whitespace", r"\s+", " "),
    Strip(),
)


@dataclass(frozen=True)
class RuleChange:
    rule: str
    before: str
    after: str


@dataclass(frozen=True)
class NormalizedText:
    source_text: str
    normalized_text: str
    changes: tuple[RuleChange, ...]
    normalizer_version: str


class Normalizer:
    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES):
        names = [r.name for r in rules]
        if len(set(names)) != len(names):
            raise ValueError("rule names must be unique")
        self.rules = rules
        # Changes whenever the rule list changes; usable as a cache key component.
        self.version = hashlib.sha256(repr(rules).encode("utf-8")).hexdigest()[:12]

    def normalize(self, source_text: str) -> NormalizedText:
        text = source_text
        changes: list[RuleChange] = []
        for rule in self.rules:
            result = rule.apply(text)
            if result != text:
                changes.append(RuleChange(rule.name, text, result))
                text = result
        return NormalizedText(source_text, text, tuple(changes), self.version)


def find_unexpanded_numbers(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, match) for digit sequences left in `text`."""
    return [(m.start(), m.end(), m.group()) for m in _NUMBER_RE.finditer(text)]
