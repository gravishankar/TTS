# Tamil Accessible TTS

A reproducible pipeline that turns verified Tamil text into speech that elderly and visually
impaired Tamil listeners can follow comfortably over long listening sessions. The pipeline is
measured on frozen evaluation data.

**Status:** planning. The requirements and project rules are in place; the TTS code is not
written yet.

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
- [CLAUDE.md](CLAUDE.md): rules for coding agents ([AGENTS.md](AGENTS.md) points to it)

## Data safety

- TAM recordings stay on the user's Mac. Committed manifests reference them through environment
  variables such as `${TAM_AUDIO_ROOT}`, never personal paths.
- `.gitignore` excludes audio, model files, checkpoints, caches, local data and credentials.
- TEST and CHALLENGE splits are never used for training.

## Other contents

`agent-sdk-course/` is an unrelated Claude Agent SDK course that predates this project. It is not
part of the TTS system.

## Licence

**OPEN QUESTION:** not decided yet.
