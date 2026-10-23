import unicodedata

from tamil_tts.frontend.normalize import Normalizer, RegexRule, find_unexpanded_numbers

KO_NFD = "கொ"  # க + ெ + ா
KO_NFC = "கொ"  # கொ


def test_nfc_composes_tamil_vowel_signs():
    assert unicodedata.normalize("NFC", KO_NFD) == KO_NFC
    result = Normalizer().normalize(KO_NFD)
    assert result.normalized_text == KO_NFC
    assert result.source_text == KO_NFD
    assert [c.rule for c in result.changes] == ["unicode-nfc"]


def test_whitespace_rules_are_audited():
    result = Normalizer().normalize("  இன்று\tகாலை\n மழை  ")
    assert result.normalized_text == "இன்று காலை மழை"
    assert [c.rule for c in result.changes] == ["collapse-whitespace", "strip"]
    assert result.changes[0].before == "  இன்று\tகாலை\n மழை  "


def test_unchanged_text_has_no_changes():
    result = Normalizer().normalize("அம்மா சுவையான உணவு சமைத்தார்.")
    assert result.changes == ()


def test_deterministic_and_versioned():
    a, b = Normalizer(), Normalizer()
    assert a.version == b.version
    assert a.normalize(KO_NFD) == b.normalize(KO_NFD)
    custom = Normalizer((RegexRule("demo", "x", "y"),))
    assert custom.version != a.version


def test_duplicate_rule_names_rejected():
    import pytest

    with pytest.raises(ValueError):
        Normalizer((RegexRule("r", "a", "b"), RegexRule("r", "c", "d")))


def test_find_unexpanded_numbers():
    found = find_unexpanded_numbers("அப்பா 3.5 கிலோ, ௨௫ ரூபாய்")
    assert [m for _, _, m in found] == ["3.5", "௨௫"]
