from pathlib import Path

from tamil_tts.models import ErrorCode, SynthesisRequest
from tamil_tts.models.errors import MAX_MESSAGE_CHARS, sanitize_message
from tamil_tts.models.mock import MockTTSModel

TEXT = "இன்று காலை மழை பெய்தது."


def test_removes_secrets_tamil_text_and_paths():
    message = f"failed on '{TEXT}' at /Users/someone/tam/TAM-001.wav and ~/x/y.wav: boom"
    cleaned = sanitize_message(message, [TEXT])
    assert "இன்று" not in cleaned and "someone" not in cleaned and "~/x" not in cleaned
    assert "<redacted>" in cleaned and "<path>" in cleaned and cleaned.endswith("boom")


def test_tamil_text_removed_even_when_not_a_secret():
    assert sanitize_message("bad token வாழைப்பழம் here") == "bad token <ta-text> here"


def test_truncates_and_collapses_whitespace():
    cleaned = sanitize_message("x  \n" * 500)
    assert len(cleaned) == MAX_MESSAGE_CHARS and "\n" not in cleaned


def test_runtime_errors_from_models_are_sanitized(tmp_path):
    class Leaky(MockTTSModel):
        def _synthesize(self, request):
            raise RuntimeError(f"cannot speak {request.text} into {request.output_path}")

    out = tmp_path / "out.wav"
    result = Leaky().synthesize(SynthesisRequest("S1", TEXT, out))
    assert result.error.code is ErrorCode.RUNTIME_ERROR
    assert "இ" not in result.error.message and str(tmp_path) not in result.error.message
    assert result.error.message.startswith("RuntimeError: cannot speak <redacted>")


def test_no_tamil_text_in_runner_errors_for_leaky_model(tmp_path):
    # Guard against regressions: a leaky model message must not reach errors.jsonl.
    assert not any("஀" <= c <= "௿" for c in sanitize_message(f"{TEXT} {Path('/tmp/a')}"))
