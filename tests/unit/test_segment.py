import dataclasses

import pytest

from tamil_tts.frontend.segment import SegmentationError, segment_text, verify_coverage


def test_sentence_segmentation(fixtures):
    source = (fixtures / "text" / "smoke_original.txt").read_text(encoding="utf-8")
    segments = segment_text("TAM-037", source)
    assert [s.segment_text for s in segments] == [
        "இன்று காலை மழை பெய்தது.",
        "நாங்கள் வீட்டிலேயே இருந்தோம்!",
        "நீ எங்கே போனாய்?",
        "அப்பா 3.5 கிலோ அரிசி வாங்கினார்.",
    ]
    assert [s.segment_id for s in segments] == [f"TAM-037-S0{i}" for i in range(1, 5)]
    for seg in segments:
        assert source[seg.source_start : seg.source_end] == seg.source_text
        assert seg.expected_length == len(seg.segment_text)
        assert len(seg.checksum) == 64


def test_ids_and_checksums_are_stable(fixtures):
    source = (fixtures / "text" / "smoke_original.txt").read_text(encoding="utf-8")
    assert segment_text("TAM-037", source) == segment_text("TAM-037", source)


def test_long_sentence_not_split_without_threshold(fixtures):
    source = (fixtures / "text" / "long_sentence_original.txt").read_text(encoding="utf-8")
    assert len(segment_text("TAM-050", source)) == 1


def test_long_sentence_split_only_at_clause_punctuation(fixtures):
    source = (fixtures / "text" / "long_sentence_original.txt").read_text(encoding="utf-8")
    segments = segment_text("TAM-050", source, max_chars=40)
    assert len(segments) == 3
    assert segments[0].segment_text == "மாலை நேரத்தில்,"
    assert segments[1].segment_text.endswith(";")
    assert "".join(s.source_text for s in segments).replace(" ", "") == source.strip().replace(
        " ", ""
    )


def test_unsplittable_clause_kept_whole():
    source = "ஒரு மிக நீண்ட வாக்கியம் இங்கே காற்புள்ளி இல்லாமல் எழுதப்பட்டுள்ளது."
    segments = segment_text("TAM-051", source, max_chars=10)
    assert len(segments) == 1


def test_trailing_text_without_terminator_is_kept():
    segments = segment_text("TAM-052", "முதல் வாக்கியம். முடிவில்லாத வரி")
    assert segments[-1].segment_text == "முடிவில்லாத வரி"


def test_ellipsis_and_quotes():
    segments = segment_text("TAM-053", "அவர் சொன்னார்: “வா…” பிறகு போனார்.")
    assert [s.segment_text for s in segments] == ["அவர் சொன்னார்: “வா…”", "பிறகு போனார்."]


def test_empty_text_gives_no_segments():
    assert segment_text("TAM-054", "   \n") == []


def test_invalid_max_chars():
    with pytest.raises(ValueError):
        segment_text("TAM-055", "வா.", max_chars=0)


def test_coverage_detects_lost_text():
    source = "முதல் வாக்கியம். இரண்டாம் வாக்கியம்."
    segments = segment_text("TAM-056", source)
    with pytest.raises(SegmentationError, match="text lost"):
        verify_coverage(source, segments[:1])
    with pytest.raises(SegmentationError, match="text lost before"):
        verify_coverage(source, segments[1:])
    tampered = [dataclasses.replace(segments[0], source_text="வேறு"), segments[1]]
    with pytest.raises(SegmentationError, match="source offsets"):
        verify_coverage(source, tampered)
