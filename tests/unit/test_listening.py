import json
import threading
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import pytest
from listening_fixtures import MANIFEST, make_run, scales

from tamil_tts.listening.app import ListeningApp, make_server
from tamil_tts.listening.items import AudioKind, attach_text, load_run, ordered
from tamil_tts.listening.report import ExportError, export
from tamil_tts.listening.schema import public_criteria, validate_submission
from tamil_tts.listening.store import SessionError, open_session

STATIC = Path(__file__).resolve().parents[2] / "src" / "tamil_tts" / "listening" / "static"
BLIND_OK = {"ratings": {"intelligibility": "yes", "comfort": 4}}
TEXT_OK = {
    "ratings": {"pronunciation": "errors", "completeness": "yes", "comfort": 3},
    "error_categories": ["PHON-LIQUID"],
    "problem_word_indices": [1],
    "notes": "word 2 unclear",
}


def _has_tamil(text: str) -> bool:
    return any("஀" <= c <= "௿" for c in text)


@pytest.fixture
def run(tmp_path):
    run_dir = make_run(tmp_path)
    results, items = load_run(run_dir)
    return run_dir, results, {i.key: i for i in items}


# --- items -------------------------------------------------------------------------


def test_audio_kinds(run):
    _, _, items = run
    kinds = {key: item.audio_kind for key, item in items.items()}
    assert kinds["tone-a/TAM-009-S01"] is AudioKind.REAL
    assert kinds["tone-b/TAM-009-S01"] is AudioKind.MISSING
    assert kinds["tone-b/TAM-010-S01"] is AudioKind.INVALID
    assert kinds["quiet/TAM-009-S01"] is AudioKind.SILENT
    assert kinds["broken/TAM-009-S01"] is AudioKind.ERROR
    assert [i.rateable for i in items.values()].count(True) == 2


def test_mock_run_items_are_mock(tmp_path):
    _, items = load_run(make_run(tmp_path, mock=True))
    assert {i.audio_kind for i in items} == {AudioKind.MOCK}
    assert not any(i.rateable for i in items)


def test_text_attached_only_when_checksum_matches(run):
    _, _, items = run
    attached = {i.key: i for i in attach_text(list(items.values()), MANIFEST, None)}
    assert attached["tone-a/TAM-009-S01"].text.startswith("எனக்கு")
    tampered = attach_text(list(items.values()), MANIFEST, 5)  # different segmentation
    assert all(
        i.text is None and "does not match" in (i.text_note or "")
        for i in tampered
        if i.segment_id == "TAM-010-S01"
    )


def test_order_is_stable_per_seed(run):
    _, _, items = run
    values = list(items.values())
    assert ordered(values, "s1") == ordered(list(reversed(values)), "s1")


# --- validation --------------------------------------------------------------------


def _text_items(run):
    _, _, items = run
    return {i.key: i for i in attach_text(list(items.values()), MANIFEST, None)}


def test_valid_submissions(run):
    _, _, items = run
    assert validate_submission(BLIND_OK, items["tone-a/TAM-009-S01"], "blind", scales()) == []
    text_items = _text_items(run)
    assert validate_submission(TEXT_OK, text_items["tone-a/TAM-009-S01"], "text", scales()) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"ratings": {"intelligibility": "yes"}}, "'comfort' is required"),
        ({"ratings": {"intelligibility": "maybe", "comfort": 4}}, "must be one of"),
        ({"ratings": {"intelligibility": "yes", "comfort": 0}}, "integer from 1 to 5"),
        ({"ratings": {"intelligibility": "yes", "comfort": 6}}, "integer from 1 to 5"),
        ({"ratings": {"intelligibility": "yes", "comfort": "4"}}, "integer from 1 to 5"),
        ({"ratings": {"intelligibility": "yes", "comfort": True}}, "integer from 1 to 5"),
        ({"ratings": {"intelligibility": "yes", "comfort": 4, "naturalness": 3}}, "TBD"),
        (
            {"ratings": {"intelligibility": "yes", "comfort": 4, "pronunciation": "correct"}},
            "not collected in blind mode",
        ),
        ({**BLIND_OK, "problem_word_indices": [0]}, "need visible text"),
        ({**BLIND_OK, "error_categories": ["NOT-A-TAG"]}, "unknown error categories"),
        ({**BLIND_OK, "notes": "x" * 1001}, "at most 1000"),
        ({**BLIND_OK, "speaker_name": "x"}, "unexpected field"),
        ("not an object", "JSON object"),
    ],
)
def test_invalid_blind_submissions(run, change, message):
    _, _, items = run
    problems = validate_submission(change, items["tone-a/TAM-009-S01"], "blind", scales())
    assert any(message in p for p in problems), problems


def test_invalid_text_submissions(run):
    item = _text_items(run)["tone-a/TAM-009-S01"]
    no_category = {**TEXT_OK, "error_categories": []}
    assert any(
        "at least one error category" in p
        for p in validate_submission(no_category, item, "text", scales())
    )
    out_of_range = {**TEXT_OK, "problem_word_indices": [99]}
    assert any(
        "out of range" in p for p in validate_submission(out_of_range, item, "text", scales())
    )
    severity = {**TEXT_OK, "ratings": {**TEXT_OK["ratings"], "pronunciation_severity": 2}}
    assert any("TBD" in p for p in validate_submission(severity, item, "text", scales()))


def test_unrateable_items_rejected(run, tmp_path):
    _, _, items = run
    for key, label in [
        ("tone-b/TAM-009-S01", "missing"),
        ("tone-b/TAM-010-S01", "invalid"),
        ("quiet/TAM-009-S01", "silent"),
        ("broken/TAM-009-S01", "failed"),
    ]:
        problems = validate_submission(BLIND_OK, items[key], "blind", scales())
        assert problems and label in problems[0].lower(), problems
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    _, mock_items = load_run(make_run(mock_dir, mock=True))
    problems = validate_submission(BLIND_OK, mock_items[0], "blind", scales())
    assert "Mock audio" in problems[0]
    assert validate_submission(BLIND_OK, None, "blind", scales()) == ["unknown item"]


def test_tbd_criteria_marked_for_page():
    names = {c["name"]: c for c in public_criteria(scales(), "text")}
    assert names["naturalness"]["type"] == "TBD" and names["naturalness"]["required"] is False
    assert names["comfort"]["min"] == 1 and names["comfort"]["max"] == 5


# --- sessions ----------------------------------------------------------------------


def _open(run_dir, **kwargs):
    defaults = {"experiment": "EXP-001", "run_id": "r1", "reviewer_id": "REV-01", "mode": "blind"}
    return open_session(run_dir, **{**defaults, **kwargs})


def test_save_and_resume(run):
    run_dir, _, items = run
    session, resumed = _open(run_dir, session_id="s1")
    assert not resumed
    item = items["tone-a/TAM-009-S01"]
    session.append(item, BLIND_OK)
    session.append(item, {"ratings": {"intelligibility": "no", "comfort": 2}})
    again, resumed = _open(run_dir, session_id="s1")
    assert resumed and len(again.records()) == 2  # append-only
    assert again.latest()[item.key]["ratings"] == {"intelligibility": "no", "comfort": 2}
    meta_before = (again.directory / "session.json").read_text()
    _open(run_dir, session_id="s1")
    assert (again.directory / "session.json").read_text() == meta_before


def test_session_rules(run):
    run_dir, _, _ = run
    _open(run_dir, session_id="s2")
    with pytest.raises(SessionError, match="belongs to"):
        _open(run_dir, session_id="s2", reviewer_id="REV-02")
    with pytest.raises(SessionError, match="belongs to"):
        _open(run_dir, session_id="s2", mode="text")
    with pytest.raises(SessionError, match="pseudonymous"):
        _open(run_dir, reviewer_id="Geetha")
    with pytest.raises(SessionError, match="invalid session id"):
        _open(run_dir, session_id="../escape")


# --- export ------------------------------------------------------------------------


def test_export_privacy_and_separation(run, tmp_path):
    run_dir, results, items = run
    text_items = _text_items(run)
    blind, _ = _open(run_dir, session_id="b1")
    blind.append(items["tone-a/TAM-009-S01"], {**BLIND_OK, "notes": "private remark"})
    text, _ = _open(run_dir, session_id="t1", reviewer_id="REV-02", mode="text")
    text.append(text_items["tone-a/TAM-010-S01"], {**TEXT_OK, "notes": "வாழைப்பழம் /Users/x"})

    out, summary = export(run_dir, list(items.values()), results, "e1")
    for name in ("listener_results.jsonl", "listening_summary.json", "LISTENING_REPORT.md"):
        content = (out / name).read_text()
        assert not _has_tamil(content), name
        assert "/Users/" not in content and str(tmp_path) not in content, name
        assert "private remark" not in content, name
    records = [json.loads(x) for x in (out / "listener_results.jsonl").read_text().splitlines()]
    assert {r["reviewer_id"] for r in records} == {"REV-01", "REV-02"}
    assert all("notes" not in r for r in records)
    assert set(summary) >= {"automatic_checks", "human_judgments"}
    assert summary["human_judgments"]["tone-a"]["comfort"]["n"] == 2
    report = (out / "LISTENING_REPORT.md").read_text()
    assert report.index("Automatic checks") < report.index("Human judgments")


def test_export_never_overwrites(run):
    run_dir, results, items = run
    export(run_dir, list(items.values()), results, "same")
    with pytest.raises(ExportError, match="not overwriting"):
        export(run_dir, list(items.values()), results, "same")


def test_export_excludes_stale_and_mock_records(run):
    run_dir, results, items = run
    session, _ = _open(run_dir, session_id="s3")
    item = items["tone-a/TAM-009-S01"]
    session.append(item, BLIND_OK)
    item.audio_path.write_bytes(item.audio_path.read_bytes()[:-2] + b"\x01\x02")  # audio changed
    # A forged record claiming mock audio is real must also be excluded.
    forged = dict(session.records()[0], item="tone-a/TAM-010-S01", audio_kind="mock")
    with session.ratings_path.open("a") as handle:
        handle.write(json.dumps(forged) + "\n")
    _, fresh = load_run(run_dir)
    _, summary = export(run_dir, fresh, results, "e2")
    assert summary["records"] == 0
    assert summary["excluded"] == {"stale_audio_changed": 1, "not_real_audio": 1}


# --- HTTP server -------------------------------------------------------------------


@pytest.fixture
def server(run):
    run_dir, results, items = run

    def start(mode="blind", session_id="web"):
        values = list(items.values())
        if mode == "text":
            values = attach_text(values, MANIFEST, None)
        session, _ = _open(run_dir, session_id=session_id, mode=mode)
        app = ListeningApp(
            results=results,
            items=ordered(values, session_id),
            session=session,
            scales=scales(),
            token="t0ken",
        )
        httpd = make_server(app, 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return app, f"http://127.0.0.1:{httpd.server_address[1]}"

    started = []
    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def _request(url, data=None, headers=None, method=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_server_security_headers_and_token(server):
    _, base = server()
    status, headers, _ = _request(base + "/")
    assert status == 200 and "default-src 'none'" in headers["Content-Security-Policy"]
    assert _request(base + "/api/state")[0] == 403
    assert _request(base + "/api/state", headers={"X-Session-Token": "wrong"})[0] == 403
    assert (
        _request(base + "/api/state", headers={"X-Session-Token": "t0ken", "Host": "evil.example"})[
            0
        ]
        == 403
    )


def test_blind_state_has_no_text_or_system_names(server):
    _, base = server()
    status, _, body = _request(base + "/api/state", headers={"X-Session-Token": "t0ken"})
    assert status == 200
    text = body.decode()
    assert not _has_tamil(text)
    assert "tone-a" not in text and "TAM-009" not in text
    state = json.loads(text)
    assert {i["audio_kind"] for i in state["items"]} == {
        "real",
        "missing",
        "invalid",
        "silent",
        "error",
    }


def test_text_state_shows_text_to_reviewer(server):
    _, base = server(mode="text", session_id="web-text")
    _, _, body = _request(base + "/api/state", headers={"X-Session-Token": "t0ken"})
    assert _has_tamil(body.decode())


def test_audio_served_only_for_real_items(server):
    app, base = server()
    for index, item in enumerate(app.items):
        status, headers, _ = _request(f"{base}/audio/{index}?token=t0ken")
        if item.rateable:
            assert status == 200 and headers["Content-Type"] == "audio/wav"
        else:
            assert status == 404
    assert _request(f"{base}/audio/0")[0] == 403


def test_rating_endpoint(server):
    app, base = server()
    real = next(i for i, item in enumerate(app.items) if item.rateable)
    unrateable = next(i for i, item in enumerate(app.items) if not item.rateable)
    headers = {"X-Session-Token": "t0ken", "Content-Type": "application/json"}
    ok = _request(base + "/api/rating", json.dumps({"index": real, **BLIND_OK}).encode(), headers)
    assert ok[0] == 200 and json.loads(ok[2])["saved"] is True
    bad = _request(
        base + "/api/rating", json.dumps({"index": unrateable, **BLIND_OK}).encode(), headers
    )
    assert bad[0] == 400 and "cannot rate" in json.loads(bad[2])["errors"][0]
    form = _request(
        base + "/api/rating", b"index=1", {"X-Session-Token": "t0ken", "Content-Type": "text/plain"}
    )
    assert form[0] == 415
    assert len(app.session.records()) == 1


# --- static page accessibility ------------------------------------------------------


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text_for = {}
        self._open_button = None

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "button":
            self._open_button = dict(attrs).get("id")
            self.text_for[self._open_button] = ""

    def handle_data(self, data):
        if self._open_button is not None:
            self.text_for[self._open_button] += data

    def handle_endtag(self, tag):
        if tag == "button":
            self._open_button = None


def test_static_page_accessibility():
    html = (STATIC / "index.html").read_text()
    parser = _Collector()
    parser.feed(html)
    tags = parser.tags
    assert ("html", {"lang": "en"}) in tags
    ids_with_label = {a["for"] for t, a in tags if t == "label"}
    for tag, attrs in tags:
        if tag in ("textarea", "select") or (tag == "input" and attrs.get("type") != "hidden"):
            assert attrs.get("id") in ids_with_label, attrs
        assert int(attrs.get("tabindex", "0") or 0) <= 0, "no positive tabindex"
    for button_id, text in parser.text_for.items():
        assert text.strip(), f"button {button_id} needs a visible name"
    shortcuts = {a.get("id"): a.get("aria-keyshortcuts") for t, a in tags if t == "button"}
    assert shortcuts == {"play": "p", "replay": "r", "prev": "b", "next": "n", "save": "s"}
    assert any(a.get("role") == "status" and a.get("aria-live") == "polite" for _, a in tags)
    assert any(a.get("role") == "alert" for _, a in tags)
    assert any(t == "a" and a.get("class") == "skip-link" for t, a in tags)
    assert ("p", {"id": "ref-text", "lang": "ta"}) in tags
    for name in ("index.html", "app.js", "app.css"):
        content = (STATIC / name).read_text()
        assert "http://" not in content and "https://" not in content, name
