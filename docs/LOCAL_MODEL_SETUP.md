# Local Model Setup (MacBook Pro M4 Max, 64 GB)

This guide prepares the Mac for model verification. It installs **no model**. The model steps are
in [MODEL_VERIFICATION_CHECKLIST.md](MODEL_VERIFICATION_CHECKLIST.md).

Rules for every step:
- Do one step at a time. Compare the result with **Expected**.
- If a **STOP** condition occurs, do not continue. Record the message (without private text) and
  ask for help.
- Never put model files, audio, caches or private data inside the repository folder.

Labels:
- **VERIFIED**: the command comes from the official documentation (source given).
- **UNVERIFIED**: the command is expected to work but was not confirmed from an official source.
  Check its result carefully.

## 1. Directory layout

All local data stays outside the repository, under `$HOME`:

```
$HOME/
├── TTS/                         # the Git repository (this project). Use your real clone path.
├── tamil-tts-envs/              # one Python environment per model
│   ├── pocket-tts/              #   Python 3.11
│   └── indicf5/                 #   Python 3.10
├── tamil-tts-models/            # TAMIL_TTS_MODEL_ROOT
│   ├── huggingface/             #   HF_HOME: Hugging Face downloads (weights, model code)
│   └── src/IndicF5/             #   IndicF5 code checkout (for its reference prompts)
├── tamil-tts-cache/             # TAMIL_TTS_CACHE_ROOT: synthesis cache
├── tamil-tts-runs/              # TAMIL_TTS_OUTPUT_ROOT: experiment runs and verification outputs
│   └── verification/<model>/<date>/
└── tamil-tts-data/              # private, never in Git
    ├── tam/audio/               # TAM_AUDIO_ROOT: TAM recordings (not used for verification)
    └── private/                 # private manifest and frozen split record
```

## 2. Environment variables

| Variable | Value | Used by |
|---|---|---|
| `TAMIL_TTS_REPO` | `$HOME/TTS` (your clone path) | these instructions |
| `TAMIL_TTS_ENV_ROOT` | `$HOME/tamil-tts-envs` | model environments |
| `TAMIL_TTS_MODEL_ROOT` | `$HOME/tamil-tts-models` | model files |
| `HF_HOME` | `$TAMIL_TTS_MODEL_ROOT/huggingface` | Hugging Face downloads (standard `huggingface_hub` variable) |
| `TAMIL_TTS_CACHE_ROOT` | `$HOME/tamil-tts-cache` | synthesis cache |
| `TAMIL_TTS_OUTPUT_ROOT` | `$HOME/tamil-tts-runs` | experiment runs, verification outputs |
| `TAM_AUDIO_ROOT` | `$HOME/tamil-tts-data/tam/audio` | TAM recordings |
| `TAM_MANIFEST` | `$HOME/tamil-tts-data/private/tam_manifest.jsonl` | private manifest |
| `TAM_FROZEN_SPLITS` | `$HOME/tamil-tts-data/private/frozen_splits.json` | frozen split record |

## 3. Prepare the Mac (one time)

### Step 3.1 — Open a terminal
Working directory: any.
Open Terminal (or the Cursor terminal).

### Step 3.2 — Check the processor
Working directory: any.
```bash
uname -m
```
Expected: `arm64`.
STOP if the result is not `arm64`.

### Step 3.3 — Check that uv is installed
Working directory: any.
```bash
uv --version
```
Expected: a version number, for example `uv 0.9.x`.
If the command is not found, do Step 3.4. Otherwise go to Step 3.5.

### Step 3.4 — Install uv (only if Step 3.3 failed)
Working directory: any.
VERIFIED (official uv installer, https://docs.astral.sh/uv/getting-started/installation/):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Expected: the installer prints where it put `uv`. Close and reopen the terminal, then repeat Step
3.3.
STOP if `uv --version` still fails.

### Step 3.5 — Create the environment file
Working directory: any.
This file is outside the repository. It holds only paths, no secrets.
```bash
cat > "$HOME/.tamil-tts.env" <<'EOF'
export TAMIL_TTS_REPO="$HOME/TTS"
export TAMIL_TTS_ENV_ROOT="$HOME/tamil-tts-envs"
export TAMIL_TTS_MODEL_ROOT="$HOME/tamil-tts-models"
export HF_HOME="$TAMIL_TTS_MODEL_ROOT/huggingface"
export TAMIL_TTS_CACHE_ROOT="$HOME/tamil-tts-cache"
export TAMIL_TTS_OUTPUT_ROOT="$HOME/tamil-tts-runs"
export TAM_AUDIO_ROOT="$HOME/tamil-tts-data/tam/audio"
export TAM_MANIFEST="$HOME/tamil-tts-data/private/tam_manifest.jsonl"
export TAM_FROZEN_SPLITS="$HOME/tamil-tts-data/private/frozen_splits.json"
EOF
```
If your repository clone is not at `$HOME/TTS`, edit the first line of the file.

### Step 3.6 — Load the environment file
Working directory: any.
Do this in every new terminal before you work on this project.
```bash
source "$HOME/.tamil-tts.env"
```
Expected: no output.

### Step 3.7 — Create the folders
Working directory: any.
```bash
mkdir -p "$TAMIL_TTS_ENV_ROOT" "$HF_HOME" "$TAMIL_TTS_MODEL_ROOT/src" \
  "$TAMIL_TTS_CACHE_ROOT" "$TAMIL_TTS_OUTPUT_ROOT/verification" \
  "$TAM_AUDIO_ROOT" "$HOME/tamil-tts-data/private"
```
Expected: no output.

### Step 3.8 — Set up the main project environment (Python 3.11)
Working directory: `$TAMIL_TTS_REPO`.
```bash
cd "$TAMIL_TTS_REPO"
git fetch origin
git checkout ccr-572d3e87-1asenq
git pull
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
```
Expected: the last command ends with `Installed ... packages`. `uv venv --python 3.11` downloads
Python 3.11 if it is not on the Mac. If `.venv` already exists from an earlier setup, `uv venv`
replaces it.
STOP if any command prints `error`.

### Step 3.9 — Run the project tests
Working directory: `$TAMIL_TTS_REPO`.
```bash
.venv/bin/python -m pytest
```
Expected: `... passed`, with no failures.
STOP if any test fails.

### Step 3.10 — Check the local roots
Working directory: `$TAMIL_TTS_REPO`.
```bash
.venv/bin/tamil-tts env check
```
Expected: JSON with the four roots (`audio`, `models`, `cache`, `outputs`).
STOP if it prints `error:`.

## 4. One environment per model

The candidates need different Python versions. Each model gets its own environment under
`$TAMIL_TTS_ENV_ROOT`. The main project (Python 3.11) never imports a model. Later, adapters will
start the model environment's Python as a subprocess.

| Model | Environment | Python | Source of the Python requirement |
|---|---|---|---|
| Pocket TTS Tamil | `$TAMIL_TTS_ENV_ROOT/pocket-tts` | 3.11 | PyPI `pocket-tts` 4.0.1 requires `>=3.10,<3.15` (VERIFIED) |
| IndicF5 | `$TAMIL_TTS_ENV_ROOT/indicf5` | 3.10 | README `conda create -n indicf5 python=3.10` (VERIFIED). This guide uses `uv venv --python 3.10` in place of conda (same Python version; UNVERIFIED as an equivalent) |
| Indic-Speak | not planned yet | 3.12 | `bodhan_genai` `.python-version` (VERIFIED). Its stack is CUDA/vLLM-centred, so it is not in L1/L2 |

Rules:
- Install each model only in its own environment.
- Pin every version (package version, Git commit, Hugging Face revision).
- Record `uv pip freeze` output in the verification result.

## 5. Hugging Face access

Model weights download into `HF_HOME` (`$TAMIL_TTS_MODEL_ROOT/huggingface`), outside Git.

Some repositories are **gated**: you must log in and accept terms on the model page first.

1. Open the model card in a browser and sign in to Hugging Face.
2. If the page shows an access form, read the terms. Accept them only if they allow your use.
3. Create a **read** token at https://huggingface.co/settings/tokens.
4. In the model environment, log in:
   ```bash
   hf auth login
   ```
   UNVERIFIED: the `hf` command comes from `huggingface_hub`. If it is not found, use
   `huggingface-cli login`. Paste the token when asked. Never put the token in a file in the
   repository.

## 6. How to measure a run

Use the same method for every model.

| Quantity | How | Notes |
|---|---|---|
| Elapsed time | `/usr/bin/time -l <command>` prints `real` (seconds) | macOS built-in `time` (not the shell keyword). Run the command twice: run 1 is **cold** (downloads, model load), run 2 is **warm**. Record both |
| Peak memory | `maximum resident set size` from the same `/usr/bin/time -l` output (bytes) | Whole process, including model load |
| Output duration | `.venv/bin/tamil-tts audio inspect <file.wav>` → `duration_s` | Run from `$TAMIL_TTS_REPO` |
| Real-time factor (RTF) | `tamil-tts audio inspect <file.wav> --elapsed <seconds>` → `real_time_factor` | RTF = elapsed / audio duration. Below 1.0 is faster than real time. CLI elapsed time includes model load, so it overstates RTF; the IndicF5 script also prints `generate_s` without load time |
| Silence and format | `tamil-tts audio inspect` → `status`, `sample_rate`, `format` | `status: silent` or `invalid` is a failure |

`/usr/bin/time -l` writes to stderr. To keep it with the logs, add `2> time.txt` and read the file.

## 7. Privacy rules for verification

- Use only the original sentences in `docs/verification/smoke_text_ta.txt` or the official
  examples. **Never use TAM recordings or TAM text during verification.**
- Use only voice and reference audio that the model publisher provides, or audio you are allowed
  to use.
- Keep generated audio in `$TAMIL_TTS_OUTPUT_ROOT/verification/`. Never copy it into the
  repository.
- In result files, write paths relative to `$HOME`. Do not paste long logs. Copy only the short
  error line.
