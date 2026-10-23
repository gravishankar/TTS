# Architecture

Derived from [PRD.md](PRD.md). Section references (§) point to the PRD. This document describes the
planned design; none of it is implemented yet.

## 1. Principle: Git is the control plane (§2)

Git carries instructions, code and compact evidence. It does not carry the model/audio workload.

| Committed | Local only (never committed) |
|---|---|
| Source code, tests | TAM WAV recordings |
| Manifests without private binary audio | Model weights |
| Experiment plans and configs | Checkpoints |
| Normalization rules, pronunciation lexicon metadata | Generated WAV/MP3 |
| Metrics, error annotations, concise reports | ASR caches, large intermediate datasets |

Every experiment is reproducible from a committed config plus documented local environment and
model identifiers.

## 2. Execution environments (§1, §3)

```
GitHub repository (control plane)
│
├──────────────► Claude Code Cloud
│                code / tests / experiment plans
│                analyze results / propose next change
▼
Local MacBook Pro M4 Max  (Cursor + local Claude Code)
tamil-tts experiment run EXP-xxx
├─ load local TAM audio
├─ load local TTS model
├─ synthesize/cache audio
├─ completeness + ASR checks
├─ human listening UI
└─ write compact result artifacts ──► commit results.json, errors.jsonl, REPORT.md
                                      └──► Claude Code Cloud analyses them
```

| Concern | Claude Code Cloud | Local M4 Max |
|---|---|---|
| Code | Design, implement, refactor, test | Pull and execute |
| Tamil front end | Normalization/segmentation/lexicon | Run against real text |
| Models | Adapters/configs; never assume APIs | Install/run models |
| TAM corpus | Manifest/schema/validation logic | Raw WAV recordings |
| Inference | Runner/config | Generate audio |
| Fine-tuning | Scripts/configs/guards | Compute-heavy tuning |
| Evaluation | Metrics/reporting | ASR/audio checks, human listening |

## 3. Components

### 3.1 Tamil speech front end (§10)
- Keeps `source_text`, `normalized_text` and `segment_text` separately.
- Deterministic, auditable Unicode normalization.
- Explicit rules for numbers, dates, currency and units.
- Pronunciation overrides from a versioned lexicon with provenance
  (`lexicon/pronunciation.jsonl`, `lexicon/proper_names.jsonl`).
- Segments at sentence boundaries; long clauses are split only at safe punctuation or configured
  thresholds.
- Each segment has an immutable `segment_id`, source offsets, a checksum and the expected text
  length. No text may disappear during segmentation.

### 3.2 Common model adapter (§11)
The interface is conceptually equivalent to:

```python
class TTSModel(Protocol):
    def status(self) -> ModelStatus: ...
    def synthesize(self, text: str, output_path: Path, **opts) -> SynthesisResult: ...
    def version_info(self) -> dict: ...
    def supports_reference_audio(self) -> bool: ...
```

- Adapters: Pocket TTS Tamil, IndicF5, Indic-Speak. Model-specific logic stays inside the adapters.
- Each adapter's internals are written only after the model's authoritative source/documentation
  has been verified. Indic-Speak may report unavailable/unsupported.
- Cloud tests use mocks/stubs; `status()` lets code run without pretending a model exists.

### 3.3 Local experiment runner (§12, §13)
The CLI is the stable interface:

```bash
tamil-tts experiment run EXP-001 [--smoke]
tamil-tts experiment status EXP-001
tamil-tts listen EXP-001
tamil-tts eval report EXP-001
tamil-tts compare EXP-001 EXP-002
tamil-tts release-check EXP-004
```

Run pipeline: validate config + manifest → resolve local roots → verify model availability/version
→ normalize + segment → hash model/config/text → reuse cached synthesis on hash match → synthesize
missing segments → verify every segment produced audio → duration/silence sanity checks → optional
local ASR comparison → write `metrics.json`, `errors.jsonl` → generate `REPORT.md`. Audio is never
committed automatically.

### 3.4 Evaluation and reporting (§15, §16)
- Per experiment: `PLAN.md`, `config.yaml`, `results.json`, `errors.jsonl`,
  `listener_results.jsonl` (when human evaluation exists) and `REPORT.md`.
- Metrics are reported separately, never as a composite score; see the gates in §16.
- Synthesis and ASR are cached by model/config/text checksum (§19).

### 3.5 Human listening interface (§17)
A local-only browser app launched with `tamil-tts listen`. See [ACCESSIBILITY.md](ACCESSIBILITY.md).

### 3.6 Fine-tuning (§18)
Scripts and configs are prepared in the cloud and executed locally. Checkpoints go to
`.local/checkpoints/`; baseline, best and last are kept. TRAIN supplies gradient updates and
VALIDATE selects; TEST and CHALLENGE never participate. Fine-tuning is blocked until EXP-001..003
have committed evidence (§14).

## 4. Data contract (§7, §8)

Manifest line (`data/manifests/tam.jsonl`):

```json
{"id":"TAM-001","split":"train","text":"<Tamil>","audio":"${TAM_AUDIO_ROOT}/TAM-001.wav","speaker_id":"SPK-01","tags":["literary","PHON-LIQUID"],"quality":"accepted"}
```

Local environment variables: `TAM_AUDIO_ROOT`, `TAMIL_TTS_MODEL_ROOT`, `TAMIL_TTS_CACHE_ROOT`.

| Split | Target | Used for training? |
|---|---|---|
| TRAIN | ~70% | Yes |
| VALIDATE | ~10% | Selection only |
| TEST | ~10% | Never; frozen after EXP-001 |
| CHALLENGE | ~10% | Never; at least half the duration is literary/book prose |

Splits are made by speaker where feasible, with duplicate and near-duplicate text removed. New
failures go to a versioned future challenge set, never to TRAIN.

## 5. Planned repository layout

PRD §6 names the root `tamil-accessible-tts/`. This repository (`gravishankar/TTS`) is used as that
root. Additions beyond §6 are marked ✱.

```
CLAUDE.md ✱               # standing agent contract
AGENTS.md                 # points to CLAUDE.md
README.md
pyproject.toml
.gitignore
docs/ ✱                   # PRD.md, ARCHITECTURE.md, ACCESSIBILITY.md
configs/{models,eval,release_gates}.yaml
data/manifests/tam.jsonl
data/text/{smoke,test,challenge}/
lexicon/{pronunciation,proper_names}.jsonl
src/tamil_tts/
  frontend/{normalize,segment,numbers,lexicon}.py
  models/{base,pocket,indicf5,indicspeak}.py
  eval/{completeness,asr,metrics,report}.py
  listening/app.py
  cli.py
tests/{unit,regression}/
experiments/EXP-00N/{PLAN.md,config.yaml,results.json,errors.jsonl,REPORT.md}
scripts/run_local.sh
.local/                   # NEVER COMMIT: datasets/tam/audio, models, checkpoints, audio, cache
agent-sdk-course/ ✱       # unrelated pre-existing course; untouched
```

## Open questions

Things the PRD does not specify. These must not be assumed in code.

1. **OPEN QUESTION:** Agent contract file. PRD §19–20 make `AGENTS.md` the standing contract,
   but the user directed that `CLAUDE.md` holds the rules and `AGENTS.md` points to it. That is the
   current setup. Should it stay this way?
2. **OPEN QUESTION:** Python version, package/environment manager, and dependency set for
   `pyproject.toml`.
3. **OPEN QUESTION:** Authoritative sources (repository/model card, version, licence) for Pocket
   TTS Tamil, IndicF5 and Indic-Speak. Each must be verified before its adapter is written.
4. **OPEN QUESTION:** Which ASR model to use for the optional local ASR comparison.
5. **OPEN QUESTION:** Segmentation thresholds (maximum segment length, safe punctuation set).
6. **OPEN QUESTION:** Thresholds for the duration/silence sanity checks.
7. **OPEN QUESTION:** Definition of "material regression" for the frozen-regression gate.
8. **OPEN QUESTION:** Which baseline is the "selected baseline" for the ≥30% pronunciation-error
   reduction (to be recalibrated after EXP-001).
9. **OPEN QUESTION:** How "IndicF5 standard reference" is defined, and how TAM reference prompts
   are selected for EXP-001.
10. **OPEN QUESTION:** Whether Tamil text in `data/text/` and in manifests (book prose, TAM
    transcripts) may be committed to this public repository, given copyright and privacy. Whether
    `speaker_id` values need pseudonymisation.
11. **OPEN QUESTION:** Size of the TAM corpus, the number of speakers, and recording format
    (sample rate, channels).
12. **OPEN QUESTION:** Output audio format for listeners, and the end-user playback target (the PRD
    requires "offline-capable" without naming a device).
13. **OPEN QUESTION:** The `.local/` folder in the repo (§6) and the `$HOME/...` roots (§7) are
    both described. Which one is canonical? Both are git-ignored.
14. **OPEN QUESTION:** Project licence (deferred by the user).
