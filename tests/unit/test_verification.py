import copy
import py_compile
from pathlib import Path

import pytest
import yaml

from tamil_tts.cli import main
from tamil_tts.verification import validate_verification_result

REPO = Path(__file__).resolve().parents[2]
VERIFICATION = REPO / "docs" / "verification"


@pytest.fixture
def template():
    return yaml.safe_load((VERIFICATION / "TEMPLATE.yaml").read_text(encoding="utf-8"))


def _filled(template):
    data = copy.deepcopy(template)
    data["date"] = "2026-10-24"
    data["overall_status"] = "VERIFIED"
    data["source"]["weights_revision"] = "80c7f2835138c62750d76a93d4333c5c5bb6a754"
    data["license"]["weights"] = "CC-BY-4.0"
    data["license"]["permits_evaluation"] = True
    data["interface"]["status"] = "VERIFIED"
    data["interface"]["invocation"] = (
        "pocket-tts generate --config ... --text ... --output-path ..."
    )
    data["smoke_tests"][0]["status"] = "PASS"
    data["smoke_tests"][0]["listening"]["all_words_spoken"] = True
    return data


def test_template_has_only_the_date_placeholder_problem(template):
    assert validate_verification_result(template) == ["date must be YYYY-MM-DD"]


def test_complete_verified_result(template):
    assert validate_verification_result(_filled(template)) == []


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("source", "weights_revision"), "main", "40-character SHA"),
        (("license", "weights"), "", "license.weights"),
        (("license", "permits_evaluation"), "unknown", "permits_evaluation"),
        (("interface", "status"), "UNVERIFIED", "interface.status"),
    ],
)
def test_verified_requirements(template, path, value, message):
    data = _filled(template)
    data[path[0]][path[1]] = value
    assert any(message in p for p in validate_verification_result(data))


def test_verified_needs_listening(template):
    data = _filled(template)
    data["smoke_tests"][0]["listening"]["all_words_spoken"] = "unknown"
    assert any("all_words_spoken" in p for p in validate_verification_result(data))


def test_absolute_paths_rejected(template):
    data = _filled(template)
    data["environment"]["env_path"] = "/Users/someone/tamil-tts-envs/pocket-tts"
    assert any("absolute path" in p for p in validate_verification_result(data))


def test_failed_needs_reason_and_statuses_checked(template):
    data = _filled(template)
    data["overall_status"] = "FAILED"
    data["smoke_tests"][0]["status"] = "OK"
    problems = validate_verification_result(data)
    assert any("stop_reason" in p for p in problems)
    assert any("smoke_tests[0].status" in p for p in problems)
    assert validate_verification_result({"model": "x"})[0].startswith("missing section")
    assert validate_verification_result([]) == ["result must be a mapping"]


def test_verify_result_cli(template, tmp_path, capsys):
    path = tmp_path / "r.yaml"
    path.write_text(yaml.safe_dump(_filled(template), allow_unicode=True))
    assert main(["verify", "result", str(path)]) == 0
    assert main(["verify", "result", str(VERIFICATION / "TEMPLATE.yaml")]) == 1


def test_smoke_text_is_short_original_tamil():
    lines = (VERIFICATION / "smoke_text_ta.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(any("஀" <= c <= "௿" for c in line) and len(line) < 60 for line in lines)
    assert not any(c.isdigit() for line in lines for c in line)


def test_indicf5_reference_transcript_present():
    text = (VERIFICATION / "indicf5_ref_PAN_F_HAPPY_00001.txt").read_text(encoding="utf-8")
    assert text.strip().endswith("।")


def test_verification_script_compiles():
    py_compile.compile(str(REPO / "scripts" / "verify" / "indicf5_smoke.py"), doraise=True)
