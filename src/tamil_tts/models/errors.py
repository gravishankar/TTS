"""Sanitize model error messages before they reach result files.

Model and subprocess errors can echo their input. Results are meant to be reviewable and
committable, so messages are scrubbed of the request's text, transcripts and paths, of
any Tamil-script characters, and of absolute paths, then truncated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MAX_MESSAGE_CHARS = 300
_TAMIL_RUN = re.compile(r"[஀-௿]+(?:\s+[஀-௿]+)*")
_ABS_PATH = re.compile(r"(?:~|/(?:Users|home|private|var|tmp|Volumes|opt|root))(?:/[^\s'\":,;)]*)+")


def sanitize_message(message: str, secrets: Iterable[str] = ()) -> str:
    """Return `message` with secrets, Tamil text and absolute paths replaced."""
    text = message
    for secret in sorted((s for s in secrets if s and s.strip()), key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    text = _TAMIL_RUN.sub("<ta-text>", text)
    text = _ABS_PATH.sub("<path>", text)
    text = " ".join(text.split())
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1] + "…"
    return text
