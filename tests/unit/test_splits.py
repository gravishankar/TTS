import dataclasses

import pytest

from tamil_tts.manifest import load_manifest
from tamil_tts.splits import (
    SplitGuardError,
    assert_no_protected,
    check_frozen,
    check_leakage,
    freeze_splits,
    split_counts,
    split_shares,
    training_entries,
)


@pytest.fixture
def entries(fixtures):
    return load_manifest(fixtures / "manifests" / "valid.jsonl").entries


def _replace(entries, entry_id, **changes):
    return [dataclasses.replace(e, **changes) if e.id == entry_id else e for e in entries]


def test_counts_and_shares(entries):
    assert split_counts(entries) == {"train": 7, "validate": 1, "test": 1, "challenge": 1}
    assert split_shares(entries)["train"] == pytest.approx(0.7)


def test_clean_fixture_has_no_leakage(entries):
    issues = check_leakage(entries, near_duplicate_threshold=0.9)
    assert issues == []


def test_near_duplicate_check_skipped_when_tbd(entries):
    issues = check_leakage(entries, None)
    assert [i.severity for i in issues] == ["warning"]
    assert "TBD" in issues[0].message


def test_identical_text_across_splits(entries):
    leaked = _replace(entries, "TAM-009", text="  இன்று காலை  மழை பெய்தது. ")
    errors = [i for i in check_leakage(leaked, None) if i.severity == "error"]
    assert len(errors) == 1 and "TAM-001" in errors[0].message


def test_near_duplicate_text(entries):
    leaked = _replace(entries, "TAM-009", text="இன்று காலை மழை பெய்தது!")
    errors = [i for i in check_leakage(leaked, 0.9) if i.severity == "error"]
    assert errors and "near-duplicate" in errors[0].message


def test_speaker_overlap_warns(entries):
    overlapped = _replace(entries, "TAM-009", speaker_id="SPK-01")
    warnings = [i.message for i in check_leakage(overlapped, 0.9)]
    assert any("SPK-01" in w for w in warnings)


def test_freeze_and_check(entries):
    frozen = freeze_splits(entries)
    assert "text" not in str(frozen)
    assert check_frozen(entries, frozen) == []


def test_frozen_changes_detected(entries):
    frozen = freeze_splits(entries)
    moved = _replace(entries, "TAM-009", split="train")
    assert "test -> train" in check_frozen(moved, frozen)[0].message
    removed = [e for e in entries if e.id != "TAM-010"]
    assert "removed" in check_frozen(removed, frozen)[0].message
    extra = dataclasses.replace(entries[0], id="TAM-011", split="challenge")
    assert "versioned future" in check_frozen([*entries, extra], frozen)[0].message
    new_train = dataclasses.replace(entries[0], id="TAM-012", split="train")
    assert check_frozen([*entries, new_train], frozen) == []


def test_tampered_freeze_record(entries):
    frozen = freeze_splits(entries)
    frozen["membership"]["TAM-009"] = "train"
    assert "checksum" in check_frozen(entries, frozen)[0].message


def test_training_guard(entries):
    train = training_entries(entries)
    assert {e.split for e in train} == {"train"} and len(train) == 7
    no_permission = _replace(entries, "TAM-003", permissions=())
    with pytest.raises(SplitGuardError, match="TAM-003"):
        training_entries(no_permission)


def test_protected_guard(entries):
    with pytest.raises(SplitGuardError, match="TAM-009, TAM-010"):
        assert_no_protected(entries)
    assert_no_protected([e for e in entries if e.split == "train"])
