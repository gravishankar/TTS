import struct
import wave

from tamil_tts.eval.completeness import (
    AudioCheckError,
    SegmentAudioStatus,
    check_segment_audio,
    inspect_wav,
)


def _pcm(path, frames: bytes, rate=16_000, width=2):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return path


def _float_wav(path, samples, rate=24_000):
    data = struct.pack(f"<{len(samples)}f", *samples)
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"LIST" + struct.pack("<I", 3) + b"abc\x00"  # odd-sized extra chunk + pad
    body += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def test_pcm_with_signal_is_ok(tmp_path):
    frames = struct.pack("<4h", 0, 1200, -1200, 0) * 4000
    check = check_segment_audio(_pcm(tmp_path / "a.wav", frames))
    assert check.ok and check.sample_rate == 16_000
    assert check.duration_s == 1.0


def test_digital_silence_detected(tmp_path):
    check = check_segment_audio(_pcm(tmp_path / "s.wav", b"\x00\x00" * 1600))
    assert check.status is SegmentAudioStatus.SILENT


def test_8bit_silence_is_0x80(tmp_path):
    assert check_segment_audio(_pcm(tmp_path / "s8.wav", b"\x80" * 800, width=1)).status is (
        SegmentAudioStatus.SILENT
    )
    assert check_segment_audio(_pcm(tmp_path / "n8.wav", b"\x80\x90" * 400, width=1)).ok


def test_float_wav_supported(tmp_path):
    info = inspect_wav(_float_wav(tmp_path / "f.wav", [0.0, 0.25, -0.25] * 8000))
    assert info.format_tag == 3 and info.duration_s == 1.0 and not info.digital_silence
    silent = check_segment_audio(_float_wav(tmp_path / "fs.wav", [0.0] * 2400))
    assert silent.status is SegmentAudioStatus.SILENT


def test_missing_empty_and_invalid(tmp_path):
    assert check_segment_audio(None).status is SegmentAudioStatus.MISSING
    assert check_segment_audio(tmp_path / "nope.wav").status is SegmentAudioStatus.MISSING
    assert check_segment_audio(_pcm(tmp_path / "e.wav", b"")).status is SegmentAudioStatus.EMPTY
    (tmp_path / "bad.wav").write_bytes(b"not a wav at all")
    assert check_segment_audio(tmp_path / "bad.wav").status is SegmentAudioStatus.INVALID
    truncated = _pcm(tmp_path / "t.wav", b"\x01\x00" * 10).read_bytes()[:30]
    (tmp_path / "t.wav").write_bytes(truncated)
    assert check_segment_audio(tmp_path / "t.wav").status is SegmentAudioStatus.INVALID


def test_unsupported_format(tmp_path):
    fmt = struct.pack("<HHIIHH", 2, 1, 8000, 4000, 1, 4)  # ADPCM
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", 2) + b"ab"
    path = tmp_path / "adpcm.wav"
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    try:
        inspect_wav(path)
    except AudioCheckError as exc:
        assert "format tag 2" in str(exc)
    else:
        raise AssertionError("expected AudioCheckError")
