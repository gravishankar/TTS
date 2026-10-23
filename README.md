# Tamil Accessible TTS

A reproducible pipeline that turns verified Tamil text into speech that elderly and visually
impaired Tamil listeners can follow comfortably over long listening sessions. The pipeline is
measured on frozen evaluation data.

**Status:** foundation. The repository has configuration loading, TAM manifest and split
validation, the Tamil text normalization and segmentation framework, the common TTS model
interface with a silent mock, the synthesis cache and the EXP-001 experiment runner, all with unit
tests. Real model adapters are not implemented yet; every candidate reports `unverified`.

## Development (Python 3.11)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest

.venv/bin/tamil-tts manifest validate tests/fixtures/manifests/valid.jsonl
.venv/bin/tamil-tts splits check tests/fixtures/manifests/valid.jsonl
.venv/bin/tamil-tts text segment --file tests/fixtures/text/smoke_original.txt --id TAM-001
.venv/bin/tamil-tts config show      # values still marked TBD
.venv/bin/tamil-tts models status    # candidate availability
.venv/bin/tamil-tts env check        # local roots under $HOME (run on the Mac)
```

EXP-001 smoke test with the silent mock (writes only to the folders you point at):

```bash
mkdir -p ~/tamil-tts-runs ~/tamil-tts-cache
export TAMIL_TTS_OUTPUT_ROOT=~/tamil-tts-runs TAMIL_TTS_CACHE_ROOT=~/tamil-tts-cache
export TAM_MANIFEST=tests/fixtures/manifests/valid.jsonl
export TAM_FROZEN_SPLITS=~/tamil-tts-runs/fixture_frozen_splits.json
.venv/bin/tamil-tts splits freeze "$TAM_MANIFEST" --out "$TAM_FROZEN_SPLITS"
.venv/bin/tamil-tts experiment run EXP-001 --smoke --mock
```

## How the work is split

| Where | What runs there |
|---|---|
| Claude Code Cloud | Software development, tests, configs, experiment plans, analysis of compact results |
| Local MacBook Pro M4 Max (Cursor, local Claude Code) | Speech models, TAM recordings, inference, fine-tuning, ASR checks, human listening |

Git is the control plane. It carries code, configs and compact evidence (`results.json`,
`errors.jsonl`, `REPORT.md`). Audio, model weights and checkpoints never enter the repository.

## Evaluation candidates

All three share one adapter and evaluation contract but serve different product roles:

- **Pocket TTS Tamil:** small, offline, CPU-friendly deployment benchmark.
- **IndicF5:** reference-audio conditioning with TAM recordings, and the adaptation lab.
- **Indic-Speak:** audiobook-quality and long-form candidate, used only once its released
  code, weights, licence and local runtime are verified.

No model is fine-tuned before the baseline evaluation (EXP-001 to EXP-003) is complete.

## Documents

- [docs/PRD.md](docs/PRD.md): product requirements (source of truth)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system architecture and planned layout
- [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md): accessibility requirements and evaluation
- [docs/MODEL_VERIFICATION.md](docs/MODEL_VERIFICATION.md): official sources, licences and status of each candidate model
- [docs/LOCAL_MODEL_SETUP.md](docs/LOCAL_MODEL_SETUP.md): one-time Mac setup, directory layout, environment variables, measurement
- [docs/MODEL_VERIFICATION_CHECKLIST.md](docs/MODEL_VERIFICATION_CHECKLIST.md): step-by-step local verification (L1 Pocket TTS, L2 IndicF5); results go in `docs/verification/`
- [CLAUDE.md](CLAUDE.md): rules for coding agents ([AGENTS.md](AGENTS.md) points to it)

## Data safety

- TAM recordings, the real TAM manifest and all real TAM text stay on the user's Mac. Git holds
  only the manifest schema and fictional test fixtures. Manifests reference audio through
  environment variables such as `${TAM_AUDIO_ROOT}`, never personal paths.
- `.gitignore` excludes audio, model files, checkpoints, caches, local data and credentials.
- TEST and CHALLENGE splits are never used for training.

## Other contents

`agent-sdk-course/` is an unrelated Claude Agent SDK course that predates this project. It is not
part of the TTS system.

## Licence

**OPEN QUESTION:** not decided yet.
