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

**Implemented in C3** (`src/tamil_tts/models/`):
- One deliberate change from the §11 sketch: `synthesize` takes a typed `SynthesisRequest`
  (segment id, normalized text, `.wav` output path, optional `ReferenceAudio` with transcript and
  checksum) instead of `(text, output_path, **opts)`. This gives every adapter, the cache and the
  runner one validated shape. Model options live in the adapter's read-only `config`, so they are
  part of the cache key.
- `BaseTTSModel` validates requests, refuses to overwrite an existing output (§20), times the
  call, and turns failures into `SynthesisError` codes: `unavailable`, `invalid_request`,
  `unsupported_reference`, `runtime_error`, `incomplete_output`. It never raises.
- `MockTTSModel` writes digital silence labelled `mock-silence`, so its output can never pass
  for speech. `UnavailableModel` is the placeholder for every candidate until it is verified
  ([MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)).

### 3.2a Synthesis cache (§13, §19)
`src/tamil_tts/cache.py`. The key is the sha256 of canonical JSON over model id + version,
model config, normalized text, and the reference audio sha256 + transcript. Segment id and output
path are not part of the key. Entries live under `$TAMIL_TTS_CACHE_ROOT/synthesis/`; the cache
refuses a root inside the repository. Audio is copied atomically and `meta.json` is written last.
An entry with missing metadata or mismatched audio checksum counts as incomplete: it is deleted
and re-synthesized. Failed synthesis is never cached.

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

**Implemented in C4** (`src/tamil_tts/experiment/`, `src/tamil_tts/eval/`):
- `tamil-tts experiment run EXP-xxx [--smoke] [--mock] [--no-cache] [--run-id ID]`.
  `tamil-tts experiment status EXP-xxx` lists runs.
- Order: load `experiments/EXP-xxx/config.yaml` → validate the private manifest (path from
  `$TAM_MANIFEST` or `--manifest`) → require the frozen split record (`$TAM_FROZEN_SPLITS` or
  `--frozen`) and abort on any frozen-split violation or text leakage → select splits (smoke:
  `smoke.ids` or the first `smoke.max_utterances`) → segment → per system: check availability and
  resolve the reference → synthesize through the cache → check each segment's audio → write
  results.
- References: `TBD` blocks the system with a reason. `entry_id` takes a TRAIN/VALIDATE recording
  and its transcript from the manifest; TEST/CHALLENGE references are rejected.
- Blocked or unavailable systems are recorded as `not_run` with the reason; the run continues.
- Output: a new directory `$TAMIL_TTS_OUTPUT_ROOT/EXP-xxx/<run-id>/` holding `audio/`,
  `segments.jsonl`, `errors.jsonl`, `results.json` and `REPORT.md`. An existing run directory is
  never reused, and an output root inside the repository is refused.
- Result files contain ids, checksums, counts and timings only, never Tamil text, transcripts or
  absolute paths, so they can be reviewed and copied into `experiments/EXP-xxx/`. PRD §13 names
  `metrics.json`; the runner writes `results.json` as listed in §15.
- `--mock` replaces every model with the silent mock and marks the report "MOCK RUN". The
  completeness gate then reads `mock_not_evidence`: a mock result is never evidence about the
  named model (C5).
- Completeness gate values (C5): `provisional_pass` (every segment produced readable, non-silent
  audio), `fail`, `not_run`, `mock_not_evidence`. Automated checks cannot detect missing words,
  truncation or mispronunciation, so a full pass needs human listening and, later, Tamil ASR as a
  diagnostic. All numeric gate targets stay provisional until real recordings exist.
- Model error messages pass through `models/errors.sanitize_message` (removes request text,
  transcripts, paths, Tamil-script text) before they reach result files.

### 3.4 Evaluation and reporting (§15, §16)
- Per experiment: `PLAN.md`, `config.yaml`, `results.json`, `errors.jsonl`,
  `listener_results.jsonl` (when human evaluation exists) and `REPORT.md`.
- Metrics are reported separately, never as a composite score; see the gates in §16.
- Synthesis and ASR are cached by model/config/text checksum (§19).
- Completeness (`eval/completeness.py`): the audio must exist, be a readable PCM or float WAV,
  contain samples, and not be digital silence. Duration and near-silence checks wait for TBD
  thresholds.

### 3.5 Human listening interface (§17)
A local-only browser app launched with `tamil-tts listen`. See [ACCESSIBILITY.md](ACCESSIBILITY.md).

**Implemented** (`src/tamil_tts/listening/`, guide: [LISTENING.md](LISTENING.md)):
- `app.py`: standard-library HTTP server on 127.0.0.1, with a per-session token, a local Host
  check, and a strict CSP. One static page (`static/`), plain JS, no framework: native form
  controls and `<audio>` give keyboard and screen-reader support.
- `items.py`: items come from a run's `segments.jsonl` and `results.json`. Audio is re-checked and
  labelled real, mock, missing, invalid, silent or error; only real audio is served or rateable.
  Text mode attaches text from the private manifest, verified by segment checksum.
- `schema.py`: validates submissions against `configs/listening.yaml`. TBD scales are rejected.
- `store.py`: append-only sessions under `<run>/listening/sessions/`, which can be resumed.
  Each session records a random order seed. Blind ratings are final once saved (identity and text
  are revealed after saving). A reviewer with a text session cannot do blind ratings for that run.
  Mock items never enter a session.
- `report.py`: each export goes to a new folder. `listener_results.jsonl` drops notes and text.
  The summary keeps automatic checks and human judgments separate.

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

Local environment variables: `TAM_AUDIO_ROOT`, `TAMIL_TTS_MODEL_ROOT`, `TAMIL_TTS_CACHE_ROOT`,
`TAMIL_TTS_OUTPUT_ROOT` (experiment runs; added in C4). The private manifest and frozen split
record are found through `TAM_MANIFEST` and `TAM_FROZEN_SPLITS`.
These point outside the repository under `$HOME`; `tamil-tts env check` refuses roots inside it.

Implemented manifest rules (`src/tamil_tts/manifest.py`): `id` is `TAM-NNN`; `split` is one of the
four splits; `audio` starts with `${TAM_AUDIO_ROOT}/` and is `.wav`; `speaker_id` is a pseudonymous
`SPK-NN` code; tags are checked case-insensitively against §9. The optional `permissions` field
(`training`, `distribution`) was added for C2 decision 10. Training refuses entries without
`training` permission.

Frozen splits (`tamil-tts splits freeze`) record ids and splits only, never text. After freezing,
frozen ids may not move or disappear, and new ids may not enter TEST/CHALLENGE.

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

1. **RESOLVED (C2):** `CLAUDE.md` is the main instruction file; `AGENTS.md` points to it.
2. **RESOLVED (C2):** Python 3.11 with a `venv` and `pyproject.toml` (setuptools, PyYAML).
3. **PARTLY RESOLVED (C3):** Sources researched in [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md).
   **OPEN QUESTION:** Licences, pinned revisions and local feasibility still need confirming on
   the Mac. No candidate is `verified` yet.
4. **OPEN QUESTION:** Which ASR model to use for the optional local ASR comparison. None is
   selected until its Tamil support has been evaluated (C2).
5. **OPEN QUESTION:** Segmentation thresholds (maximum segment length, safe punctuation set).
6. **OPEN QUESTION:** Thresholds for the duration/silence sanity checks.
7. **OPEN QUESTION:** Definition of "material regression" for the frozen-regression gate.
8. **OPEN QUESTION:** Which baseline is the "selected baseline" for the ≥30% pronunciation-error
   reduction (to be recalibrated after EXP-001).
9. **OPEN QUESTION:** How "IndicF5 standard reference" is defined, and how TAM reference prompts
   are selected for EXP-001.
10. **RESOLVED (C2):** Copyrighted book text, private TAM transcripts and identifying speaker
    information are never committed; speaker IDs are pseudonymous. **OPEN QUESTION:** where the
    real manifest (which contains transcripts) and the TEST/CHALLENGE text are kept, and what
    committed form, if any, they take.
11. **OPEN QUESTION:** Size of the TAM corpus, the number of speakers, and recording format
    (sample rate, channels).
12. **PARTLY RESOLVED (C2):** Evaluation audio is WAV. **OPEN QUESTION:** the delivery format for
    listeners and the end-user playback target ("offline-capable" names no device).
13. **RESOLVED (C2):** Local roots live under `$HOME`, outside the repository. `.local/` stays
    git-ignored as a safety net.
14. **OPEN QUESTION:** Project licence (deferred by the user).
15. **RESOLVED (C5):** Each model gets its own environment under `$TAMIL_TTS_ENV_ROOT` (Pocket
    3.11, IndicF5 3.10). Adapters will start that environment's Python as a subprocess. Whether to
    use one process per segment or a long-lived worker is decided after L1/L2 measure load time
    ([LOCAL_MODEL_SETUP.md](LOCAL_MODEL_SETUP.md), [MODEL_VERIFICATION_CHECKLIST.md](MODEL_VERIFICATION_CHECKLIST.md) Part D).
