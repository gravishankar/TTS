"""IndicF5 smoke test for local verification (L2). Run it with the IndicF5 environment's Python.

It wraps the official README example (https://github.com/AI4Bharat/IndicF5, commit
13f7c4d627cc10111aea8fe9c0039462cacacdc7) without changing the calls:

    model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
    audio = model(text, ref_audio_path=..., ref_text=...)
    sf.write(out, audio, samplerate=24000)

Only `revision=` is added, so the Hugging Face weights and remote code can be pinned.
Text and transcripts are read from files so they do not appear in shell history or in
the process list. The script prints timings and audio facts only, never the text.
It is not an adapter and is not imported by the tamil_tts package.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ID = "ai4bharat/IndicF5"
SAMPLE_RATE = 24000  # from the official README


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--ref-audio", type=Path, required=True)
    parser.add_argument("--ref-text-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--revision", help="full commit SHA of the Hugging Face repo")
    parser.add_argument("--line", type=int, default=1, help="line of --text-file to speak")
    args = parser.parse_args()

    if args.out.exists():
        print(json.dumps({"error": "output exists; choose a new --out"}))
        return 2
    lines = [x.strip() for x in args.text_file.read_text(encoding="utf-8").splitlines()]
    lines = [x for x in lines if x]
    if not 1 <= args.line <= len(lines):
        print(json.dumps({"error": "--line out of range"}))
        return 2
    text = lines[args.line - 1]
    ref_text = args.ref_text_file.read_text(encoding="utf-8").strip()

    try:
        import numpy as np
        import soundfile as sf
        from transformers import AutoModel

        start = time.perf_counter()
        kwargs = {"trust_remote_code": True}
        if args.revision:
            kwargs["revision"] = args.revision
        model = AutoModel.from_pretrained(REPO_ID, **kwargs)
        loaded = time.perf_counter()
        audio = model(text, ref_audio_path=str(args.ref_audio), ref_text=ref_text)
        generated = time.perf_counter()
        dtype = str(audio.dtype)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        args.out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(args.out), np.array(audio, dtype=np.float32), samplerate=SAMPLE_RATE)
    except Exception as exc:  # report the type only: messages may echo text or paths
        print(json.dumps({"error": type(exc).__name__, "hint": "see the traceback above"}))
        raise

    print(
        json.dumps(
            {
                "load_s": round(loaded - start, 3),
                "generate_s": round(generated - loaded, 3),
                "samples": int(len(audio)),
                "returned_dtype": dtype,
                "sample_rate": SAMPLE_RATE,
                "duration_s": round(len(audio) / SAMPLE_RATE, 3),
                "rtf_generate": round((generated - loaded) / (len(audio) / SAMPLE_RATE), 4)
                if len(audio)
                else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
