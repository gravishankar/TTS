# Tamil Accessible TTS — Claude Cloud Contract

Standing contract for every agent working in this repository. Source of requirements:
[docs/PRD.md](docs/PRD.md). Keep this file ≤150 lines (PRD §19).

## GOAL
Improve verified Tamil text → accessible offline speech, measured on frozen TAM evaluation data.

## BOUNDARY
- Cloud (Claude Code Cloud): software development, tests, configs, experiment plans, analysis of
  compact results.
- Local (MacBook Pro M4 Max, via Cursor and local Claude Code): model installation, model
  execution, inference, fine-tuning, TAM recordings, generated audio, ASR checks, human listening.
- All TAM recordings stay on the user's Mac. Speech models run locally on the M4 Max only.
- Git is the control plane: it carries code, configs and compact evidence, never the model/audio
  workload (PRD §2).

## NON-NEGOTIABLE
- Never alter source Tamil text.
- Never train on TEST or CHALLENGE. Keep TEST and CHALLENGE data separate from training.
- Never change frozen split membership after EXP-001.
- Preserve source_text and normalized_text separately.
- Every segment is traceable by immutable ID/checksum.
- Zero missing/silent text is a hard release gate.
- Human Tamil judgments outrank ASR for pronunciation.
- Prefer deterministic front-end fixes over tuning when appropriate.
- Do not fine-tune before baseline evaluation. Do not start EXP-004 until EXP-001..003 gates are
  complete.
- Never invent model APIs or interfaces; verify authoritative docs/source.
- Never require raw audio/model weights in cloud context.
- Do not overwrite experiment outputs.
- Treat Pocket TTS Tamil, IndicF5 and Indic-Speak as first-class evaluation candidates.
- IndicF5 TAM reference prompting is required before IndicF5 fine-tuning.
- For Indic-Speak, verify current released code/API/license/local feasibility; never infer an
  interface from an announcement. An adapter that reports "unavailable" is preferable to an
  invented API.

## NEVER COMMIT
- Audio of any kind (TAM recordings, generated WAV/MP3, reference prompts).
- Model weights, checkpoints, ASR caches, synthesis caches, large intermediate datasets.
- Credentials, API keys, `.env` files, tokens.
- Personal absolute paths or other private data. Manifests use logical roots such as
  `${TAM_AUDIO_ROOT}` (PRD §7).
- Anything under `.local/`.

`.gitignore` enforces most of this; check `git status` before every commit anyway.

## CLOUD-SIDE RULES
- Do not download, install or run speech models or ASR models in the cloud.
- When a model or runtime is absent, test with mocks/stubs. Code must fail clearly when local
  roots or models are missing (PRD §7).
- Keep model-specific logic inside adapters behind the common `TTSModel` interface (PRD §11).
- The stable interface is the `tamil-tts` Python CLI; shell scripts only activate the environment
  and call it (PRD §12).
- Store results as JSON/JSONL plus concise Markdown reports generated programmatically.

## REPOSITORY
- `agent-sdk-course/` is an unrelated course. Do not modify it and do not import from it.
- Do not change the default branch. Work only on the branch assigned for the session.
- Do not add a LICENSE until the user decides on one.
- Planned layout: PRD §6, adapted in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## DECISIONS (user, C2)
- CLAUDE.md is the main instruction file; AGENTS.md points here.
- TAM recordings, models, caches and experiment runs live outside the repo under `$HOME`
  (`TAM_AUDIO_ROOT`, `TAMIL_TTS_MODEL_ROOT`, `TAMIL_TTS_CACHE_ROOT`, `TAMIL_TTS_OUTPUT_ROOT`).
  Experiment result files must stay free of Tamil text, transcripts and absolute paths.
- Never commit copyrighted book text, private TAM transcripts or identifying speaker information.
  Speaker IDs are pseudonymous codes (`SPK-01`). Test fixtures use original text only.
- Verify official model sources and licences before implementing any adapter. Record findings in
  `docs/MODEL_VERIFICATION.md`; keep `verified: false` in `configs/models.yaml` until confirmed.
- The real TAM manifest and all real TAM text stay private on the Mac. Git holds only the schema
  and fictional fixtures (C3).
- Undefined evaluation thresholds stay `TBD` in `configs/`; code must refuse to use them.
- The listening interface must be keyboard- and screen-reader accessible.
- Python 3.11 is the development target. Evaluation audio is WAV.
- Do not select an ASR model until its Tamil support has been evaluated.
- Training or distribution requires recorded permission (manifest `permissions` field).

## DEV COMMANDS
- `python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- `.venv/bin/python -m pytest` · `.venv/bin/ruff check src tests` · `.venv/bin/ruff format src tests`

## OPEN QUESTIONS
- Do not invent missing requirements. Record them as **OPEN QUESTION** in the relevant document
  and ask the user.

## WORK STYLE
- Read this file, the current experiment `PLAN.md`, and only the files relevant to the task.
- Plan ≤8 bullets; implement; test.
- Use mocks when cloud lacks local models.
- Use the 12–20 utterance smoke set while coding; full frozen evaluation only at experiment
  checkpoints.
- One concern per prompt when debugging; use compact error excerpts, not entire logs.
- End with: changed files; tests; exact local command; expected result files; blockers/next
  decision. No project-history recap.
