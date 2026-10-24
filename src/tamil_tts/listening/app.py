"""Local-only listening server (`tamil-tts listen serve`, PRD §17).

Standard library only: an HTTP server bound to 127.0.0.1 that serves one static page,
a JSON state endpoint, the audio of rateable items, and a rating endpoint.

Safeguards:
- Binds to 127.0.0.1 and rejects requests whose Host header is not local.
- Every /api and /audio request needs the per-session token printed at start-up.
- Content-Security-Policy allows only same-origin resources; the page loads nothing
  from external services.
- Items are addressed by their seeded presentation position. Model identity is sent only
  after an item's rating is saved; in blind mode the text is revealed the same way, and
  the rating is then final.
- Mock audio never enters a session. Only real audio is served or rateable.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, urlsplit

from tamil_tts.listening.items import AUDIO_KIND_TEXT, AudioKind, ListeningItem
from tamil_tts.listening.schema import public_criteria, validate_submission
from tamil_tts.listening.store import Session, SessionError
from tamil_tts.manifest import TAXONOMY_TAGS

STATIC = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "media-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
}
MAX_BODY = 64 * 1024
_LOCAL_HOST = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")


class ListeningApp:
    def __init__(
        self,
        *,
        results: Mapping[str, Any],
        items: list[ListeningItem],
        session: Session,
        scales: Mapping[str, Any],
        token: str | None = None,
        excluded_mock: int = 0,
    ):
        if results.get("mock") or any(i.audio_kind is AudioKind.MOCK for i in items):
            raise ValueError("mock audio cannot enter an evaluation session")
        self.results = results
        self.items = items  # already in session (seeded) order
        self.session = session
        self.scales = scales
        self.token = token or secrets.token_urlsafe(24)
        self.excluded_mock = excluded_mock

    def _reveal(self, item: ListeningItem) -> dict[str, Any]:
        """Shown only after the item's rating is saved."""
        reveal: dict[str, Any] = {
            "system_id": item.system_id,
            "model_id": item.model_id,
            "model_version": item.model_version,
        }
        if self.session.mode == "blind":
            reveal["text"] = item.text
            reveal["text_note"] = item.text_note if item.text is None else None
        return reveal

    def state(self) -> dict[str, Any]:
        latest = self.session.latest()
        blind = self.session.mode == "blind"
        items = []
        for index, item in enumerate(self.items):
            saved = latest.get(item.key)
            entry: dict[str, Any] = {
                "index": index,
                "number": index + 1,
                "audio_kind": item.audio_kind.value,
                "audio_label": AUDIO_KIND_TEXT[item.audio_kind],
                "rateable": item.rateable,
                "duration_s": item.duration_s,
                "saved": None
                if saved is None
                else {
                    k: saved[k]
                    for k in ("ratings", "error_categories", "problem_word_indices", "notes")
                },
                "locked": blind and saved is not None,
                "reveal": self._reveal(item) if saved is not None else None,
            }
            if not blind:
                entry["text"] = item.text
                entry["words"] = item.text.split() if item.text else []
                entry["text_note"] = item.text_note
            items.append(entry)
        rateable = sum(i.rateable for i in self.items)
        return {
            "experiment": self.results.get("experiment"),
            "run_id": self.results.get("run_id"),
            "mode": self.session.mode,
            "session_id": self.session.session_id,
            "reviewer_id": self.session.reviewer_id,
            "criteria": public_criteria(self.scales, self.session.mode),
            "taxonomy": sorted(TAXONOMY_TAGS),
            "notes_max_chars": int(self.scales.get("notes", {}).get("max_chars", 1000)),
            "excluded_mock": self.excluded_mock,
            "items": items,
            "progress": {
                "total": len(self.items),
                "rateable": rateable,
                "rated": sum(1 for i in self.items if i.key in latest and i.rateable),
            },
        }

    def submit(self, body: Any) -> tuple[int, dict[str, Any]]:
        if not isinstance(body, dict) or not isinstance(body.get("index"), int):
            return 400, {"errors": ["index is required"]}
        index = body["index"]
        item = self.items[index] if 0 <= index < len(self.items) else None
        payload = {k: v for k, v in body.items() if k != "index"}
        if item is not None and self.session.mode == "blind" and item.key in self.session.latest():
            return 409, {"errors": ["blind ratings are final once submitted"]}
        problems = validate_submission(payload, item, self.session.mode, self.scales)
        if problems:
            return 400, {"errors": problems}
        try:
            record = self.session.append(item, payload, position=index + 1)
        except SessionError as exc:
            return 400, {"errors": [str(exc)]}
        return 200, {"saved": True, "seq": record["seq"], "reveal": self._reveal(item)}


def make_handler(app: ListeningApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "tamil-tts-listen"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Log the path only: query strings carry the session token.
            print(f"{self.command} {urlsplit(self.path).path}")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, data: Any) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

        def _allowed(self, require_token: bool) -> bool:
            if not _LOCAL_HOST.match(self.headers.get("Host", "")):
                self._json(HTTPStatus.FORBIDDEN, {"errors": ["non-local host"]})
                return False
            if require_token:
                query = parse_qs(urlsplit(self.path).query)
                token = self.headers.get("X-Session-Token") or query.get("token", [""])[0]
                if not secrets.compare_digest(token, app.token):
                    self._json(HTTPStatus.FORBIDDEN, {"errors": ["missing or wrong token"]})
                    return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path in STATIC:
                if not self._allowed(require_token=False):
                    return
                name = STATIC[path]
                data = resources.files("tamil_tts.listening").joinpath("static", name).read_bytes()
                self._send(HTTPStatus.OK, data, CONTENT_TYPES["." + name.rsplit(".", 1)[1]])
            elif path == "/api/state":
                if self._allowed(require_token=True):
                    self._json(HTTPStatus.OK, app.state())
            elif path.startswith("/audio/"):
                if not self._allowed(require_token=True):
                    return
                index = path.removeprefix("/audio/")
                item = (
                    app.items[int(index)]
                    if index.isdigit() and int(index) < len(app.items)
                    else None
                )
                if item is None or not item.rateable or item.audio_path is None:
                    self._json(HTTPStatus.NOT_FOUND, {"errors": ["no playable audio"]})
                    return
                self._send(HTTPStatus.OK, item.audio_path.read_bytes(), "audio/wav")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"errors": ["not found"]})

        def do_POST(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/api/rating":
                self._json(HTTPStatus.NOT_FOUND, {"errors": ["not found"]})
                return
            if not self._allowed(require_token=True):
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"errors": ["JSON only"]})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"errors": ["bad body size"]})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"errors": ["invalid JSON"]})
                return
            status, data = app.submit(body)
            self._json(status, data)

    return Handler


def make_server(app: ListeningApp, port: int = 8765) -> ThreadingHTTPServer:
    """Create the server on 127.0.0.1 only. Port 0 picks a free port."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
