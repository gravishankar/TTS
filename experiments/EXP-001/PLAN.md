# EXP-001 — Frozen Baseline

OBJECTIVE
Measure Pocket TTS Tamil, IndicF5 (standard + selected TAM reference), and Indic-Speak on the same
frozen Tamil benchmark before any tuning.

INPUTS
- Private manifest (`$TAM_MANIFEST`) and frozen split record (`$TAM_FROZEN_SPLITS`) on the Mac
- TEST + CHALLENGE splits (`config.yaml`)
- Local roots: `TAM_AUDIO_ROOT`, `TAMIL_TTS_MODEL_ROOT`, `TAMIL_TTS_CACHE_ROOT`, `TAMIL_TTS_OUTPUT_ROOT`

ALLOWED SCOPE
Runner, adapters (after verification), cache, completeness checks, results and report generation.

LOCAL RUN
```bash
tamil-tts splits freeze "$TAM_MANIFEST" --out "$TAM_FROZEN_SPLITS"   # once, never again
tamil-tts experiment run EXP-001 --smoke
tamil-tts experiment run EXP-001
```

GATES
Completeness 100% (hard). Other gates need human listening or are TBD (configs/release_gates.yaml).

OUTPUTS TO COMMIT (after review)
`results.json`, `errors.jsonl`, `REPORT.md` from `$TAMIL_TTS_OUTPUT_ROOT/EXP-001/<run-id>/`.
They contain ids, checksums and counts only. Never commit audio.

DO NOT
fine-tune; build production UI; add database; commit audio; change source Tamil.

BLOCKERS
No candidate is verified (docs/MODEL_VERIFICATION.md); reference prompts are TBD.
