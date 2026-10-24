"""Keyboard and screen-reader checks in a real browser (skipped when Playwright is absent)."""

import threading
from pathlib import Path

import pytest
from listening_fixtures import make_run, scales

from tamil_tts.listening.app import ListeningApp, make_server
from tamil_tts.listening.items import load_run, ordered
from tamil_tts.listening.store import open_session

sync_api = pytest.importorskip("playwright.sync_api")

LOCAL_CHROMIUM = Path("/opt/pw-browsers/chromium")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except Exception:
            if not LOCAL_CHROMIUM.exists():
                pytest.skip("no Chromium available for Playwright")
            instance = p.chromium.launch(executable_path=str(LOCAL_CHROMIUM))
        yield instance
        instance.close()


@pytest.fixture
def site(tmp_path):
    run_dir = make_run(tmp_path)
    results, items = load_run(run_dir)
    session, _ = open_session(
        run_dir,
        experiment="EXP-001",
        run_id="r1",
        reviewer_id="REV-01",
        mode="blind",
        session_id="web",
    )
    app = ListeningApp(
        results=results,
        items=ordered(items, "web"),
        session=session,
        scales=scales(),
        token="t0ken",
    )
    httpd = make_server(app, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{httpd.server_address[1]}/?token=t0ken"
    httpd.shutdown()
    httpd.server_close()


def _open(browser, url):
    page = browser.new_page()
    external = []
    page.on(
        "request",
        lambda r: None if r.url.startswith("http://127.0.0.1") else external.append(r.url),
    )
    page.goto(url)
    sync_api.expect(page.locator("#item-heading")).to_contain_text(" of ")
    return page, external


def test_keyboard_navigation_and_labels(browser, site):
    app, url = site
    page, external = _open(browser, url)
    total = len(app.items)

    # First Tab reaches the skip link; activating it moves focus to the item heading.
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "item-heading"

    # Controls are exposed with accessible names.
    for name in ("Play", "Replay from start", "Previous item", "Next item", "Save rating"):
        assert page.get_by_role("button", name=name).count() >= 1, name
    assert page.get_by_role("group", name="Playback").count() == 1
    assert page.get_by_role("status").count() == 1

    # N / B shortcuts move between items and announce the change.
    first = page.text_content("#item-heading")
    page.keyboard.press("n")
    assert page.text_content("#item-heading") != first
    assert f"of {total}" in page.text_content("#item-heading")
    page.keyboard.press("b")
    assert page.text_content("#item-heading") == first
    assert "Item" in page.text_content("#status")
    assert external == []


def test_unrateable_items_are_labelled_and_disabled(browser, site):
    app, url = site
    page, _ = _open(browser, url)
    index = next(i for i, item in enumerate(app.items) if not item.rateable)
    page.get_by_role("button", name=f"Item {index + 1}:").click()
    assert "cannot be rated" in page.text_content("#audio-kind")
    assert page.is_disabled("#play") and page.is_disabled("#replay")
    assert page.is_disabled("#rating-fields input[name='comfort'] >> nth=0")
    assert page.get_attribute("#player", "src") is None


def test_rate_with_keyboard_save_and_resume(browser, site):
    app, url = site
    page, _ = _open(browser, url)
    # Blind: identity and text are hidden until the rating is saved.
    assert page.is_hidden("#reveal")
    assert page.is_hidden("#categories")
    page.get_by_role("radio", name="yes").first.focus()
    page.keyboard.press("Space")
    page.get_by_role("radio", name="4").focus()
    page.keyboard.press("Space")
    page.keyboard.press("s")  # shortcut works from a radio button
    sync_api.expect(page.locator("#status")).to_contain_text("Saved rating")
    assert len(app.session.records()) == 1
    heading = page.text_content("#item-heading")
    sync_api.expect(page.locator("#reveal-model")).to_contain_text("System: ")
    assert page.is_disabled("#rating-fields input[name='comfort'] >> nth=0")  # final

    # Missing required fields are reported in the alert region, not saved silently.
    page.keyboard.press("n")
    while page.is_disabled("#play"):
        page.keyboard.press("n")
    page.keyboard.press("s")
    sync_api.expect(page.locator("#errors")).to_contain_text("required")
    assert len(app.session.records()) == 1

    # Reloading resumes the session: the rated item keeps its values.
    resumed, _ = _open(browser, url)
    resumed.get_by_role("button", name=heading.replace(" of", ":").split(":")[0] + ":").click()
    assert resumed.is_checked("#crit-comfort-4")
    assert resumed.is_checked("#crit-perceived_intelligibility-yes")
    assert "final" in resumed.text_content("#reveal-note")
    assert "1 of" in resumed.text_content("#progress")
