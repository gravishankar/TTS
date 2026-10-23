# Model Verification Checklist

Use this checklist on the Mac to verify one model at a time. Do the one-time setup in
[LOCAL_MODEL_SETUP.md](LOCAL_MODEL_SETUP.md) first. Record every result in a copy of
[verification/TEMPLATE.yaml](verification/TEMPLATE.yaml).

Order: **L1 Pocket TTS Tamil**, then **L2 IndicF5**. Indic-Speak is not in scope yet.

Rules:
- Do one step at a time. Compare the result with **Expected**.
- If a **STOP** condition occurs, do not continue. Set `overall_status: FAILED` and write the
  `stop_reason`. Ask for help.
- **VERIFIED** commands come from the official documentation (sources at the end).
  **UNVERIFIED** commands are reasonable but not confirmed; check their results carefully.
- Use only the original sentences in `docs/verification/smoke_text_ta.txt` and publisher-provided
  voice or reference audio. Never use TAM recordings or TAM text.

A model counts as verified only when **all** of these are true:
1. The licence is read on the official card and permits evaluation.
2. Code version and weights revision are pinned to exact values.
3. The documented interface produced a WAV file from Tamil text on this Mac.
4. `tamil-tts audio inspect` reports `status: ok`.
5. A person listened and confirmed that all words were spoken.

## Part A — Check the model card, licence, revision and access

Do these steps for each model before you install it.

### A1 — Open the official model card
Open the card URL from the model's section below in a browser. Sign in to Hugging Face.
Expected: the card loads.
STOP if the page says the repository does not exist.

### A2 — Record the licence
Find the licence in the card header (the `License:` tag) and in any LICENSE file under **Files
and versions**.
Record in the result file:
- `license.weights`: the exact name.
- `license.where_stated`: where you found it.
- `license.permits_evaluation`, `license.permits_adaptation`,
  `license.permits_distribution_of_generated_audio`, `license.attribution_required`.
- `license.prohibited_use_notes`: any prohibited-use or terms-of-use text (for example, voice
  cloning only with consent).

STOP if the licence does not permit evaluation, or if no licence is stated.

### A3 — Record access restrictions
If the card shows "You need to agree to share your contact information" or a similar form, the
repository is **gated**.
Record `source.gated: yes` or `no`.
If it is gated: read the terms, then accept them only if they allow your use. Record
`source.access_terms_accepted`.
STOP if you do not accept the terms.

### A4 — Pin the weights revision
Open **Files and versions**, then **History** (the commit list).
Copy the full 40-character commit SHA of the revision you will test.
Record it in `source.weights_revision`.
Expected: a value like `80c7f2835138c62750d76a93d4333c5c5bb6a754`.

### A5 — Log in (only for gated repositories)
Do Section 5 of LOCAL_MODEL_SETUP.md, using the `hf` command from the model's environment.

## Part B — L1: Pocket TTS Tamil

Facts used here (VERIFIED, from the official Pocket TTS README and CLI reference):
- Install: `pip install pocket-tts` (Python ≥3.10, <3.15). The default macOS PyTorch wheels are
  CPU-only.
- Tamil is supported by the **community** model `Thanushttk/pocket-tts-multilingual`, loaded with
  `--config hf://Thanushttk/pocket-tts-multilingual/config.yaml@80c7f2835138c62750d76a93d4333c5c5bb6a754`.
- `generate` options: `--config`, `--voice`, `--text`, `--output-path`, `--device` (default
  `cpu`), `--quiet`.
- With `--config` and no `--voice`, the voice defaults to Kyutai's `alba` sample (an English voice).
  The README recommends an Indian voice for a better accent. L1 uses the default voice, because no
  permitted Indian voice sample is chosen yet.
- Output: WAV, 24 kHz, mono, 16-bit PCM.

Card URLs: https://huggingface.co/Thanushttk/pocket-tts-multilingual and
https://huggingface.co/kyutai/pocket-tts (upstream terms).

### L1.1 — Load the environment file
Working directory: any.
```bash
source "$HOME/.tamil-tts.env"
```

### L1.2 — Check the cards
Do Part A for `Thanushttk/pocket-tts-multilingual`. Also read the prohibited-use section of
`kyutai/pocket-tts`.
Expected: the licence (reported as CC BY 4.0) is confirmed on the card. Revision
`80c7f2835138c62750d76a93d4333c5c5bb6a754` exists in the history.
STOP if the licence is different from CC BY 4.0. Report it before you continue.

### L1.3 — Create the output folder
Working directory: any.
```bash
export V="$TAMIL_TTS_OUTPUT_ROOT/verification/pocket-tts/$(date +%F)"
mkdir -p "$V"
```

### L1.4 — Create the Pocket TTS environment (Python 3.11)
Working directory: any.
```bash
uv venv --python 3.11 "$TAMIL_TTS_ENV_ROOT/pocket-tts"
```
Expected: `Creating virtual environment at: .../tamil-tts-envs/pocket-tts`.

### L1.5 — Install the pinned package
Working directory: any.
```bash
uv pip install --python "$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/python" "pocket-tts==4.0.1"
```
Expected: `Installed ... packages`, including `pocket-tts==4.0.1` and `torch`.
STOP if the install fails.

### L1.6 — Check the documented options
Working directory: any.
```bash
"$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/pocket-tts" generate --help
```
Expected: the help lists `--config`, `--voice`, `--text` and `--output-path`.
STOP if any of these options is missing.

### L1.7 — Run smoke test S1 (cold)
Working directory: `$V`.
This run downloads the model into `HF_HOME`.
```bash
cd "$V"
/usr/bin/time -l "$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/pocket-tts" generate \
  --config "hf://Thanushttk/pocket-tts-multilingual/config.yaml@80c7f2835138c62750d76a93d4333c5c5bb6a754" \
  --text "$(sed -n 1p "$TAMIL_TTS_REPO/docs/verification/smoke_text_ta.txt")" \
  --output-path "$V/s1_cold.wav" 2> "$V/s1_cold.log"
```
Expected: the command ends without an error, and `$V/s1_cold.wav` exists.
STOP if the log contains `401`, `403`, `GatedRepo` or `Access`. Do step A5, then repeat L1.7.
STOP on any other error. Copy only the last error line into the result file.

### L1.8 — Read the cold timing
Working directory: `$V`.
```bash
grep -E " real |maximum resident set size" "$V/s1_cold.log"
```
Expected: one line with `real` (seconds) and one line with the peak memory in bytes.
Record them as `cold_elapsed_s` and `peak_rss_bytes`.

### L1.9 — Run smoke test S1 again (warm, offline)
Working directory: `$V`.
`HF_HUB_OFFLINE=1` stops Hugging Face downloads. This checks that the model runs without the
network (UNVERIFIED that pocket-tts honours it; it uses the Hugging Face cache).
```bash
HF_HUB_OFFLINE=1 /usr/bin/time -l "$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/pocket-tts" generate \
  --config "hf://Thanushttk/pocket-tts-multilingual/config.yaml@80c7f2835138c62750d76a93d4333c5c5bb6a754" \
  --text "$(sed -n 1p "$TAMIL_TTS_REPO/docs/verification/smoke_text_ta.txt")" \
  --output-path "$V/s1_warm.wav" 2> "$V/s1_warm.log"
grep -E " real |maximum resident set size" "$V/s1_warm.log"
```
Expected: `$V/s1_warm.wav` exists. Record `warm_elapsed_s`.
If it fails with an offline or connection error, run it again without `HF_HUB_OFFLINE=1`. Record
"offline: no" in `interface.differences_from_docs`.

### L1.10 — Inspect the audio
Working directory: `$TAMIL_TTS_REPO`.
Replace `<warm seconds>` with the `real` value from L1.9.
```bash
cd "$TAMIL_TTS_REPO"
.venv/bin/tamil-tts audio inspect "$V/s1_warm.wav" --elapsed <warm seconds>
```
Expected: `"status": "ok"`, `"sample_rate": 24000`, `"channels": 1`, `"bits_per_sample": 16`.
Record `output_duration_s`, `real_time_factor` and `audio_check`.
STOP if the status is `silent`, `empty` or `invalid`.

### L1.11 — Listen
Working directory: any.
```bash
afplay "$V/s1_warm.wav"
```
Read line 1 of `docs/verification/smoke_text_ta.txt` while you listen.
Record `listening.all_words_spoken`, `listening.intelligible` and short notes.
A wrong accent is expected with the English default voice. Note it, but do not fail the test for
it.

### L1.12 — Optional: smoke tests S2 and S3
Repeat L1.9 to L1.11 with `sed -n 2p` and `sed -n 3p`, and new output names (`s2_warm.wav`,
`s3_warm.wav`). Line 2 tests ழ. Line 3 tests a number written as a word.

### L1.13 — Optional: check the Python API with the community config (UNVERIFIED)
A future adapter may keep the model loaded between segments. The documented Python API is
`TTSModel.load_model(config=...)`, but the documentation says `config` is a "path to model config
YAML file". Whether it accepts an `hf://` path is UNVERIFIED.
Working directory: `$V`.
```bash
HF_HUB_OFFLINE=1 "$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/python" - <<'EOF'
from pocket_tts import TTSModel
model = TTSModel.load_model(
    config="hf://Thanushttk/pocket-tts-multilingual/config.yaml@80c7f2835138c62750d76a93d4333c5c5bb6a754"
)
print("sample_rate", model.sample_rate, "device", model.device)
EOF
```
Expected (if supported): `sample_rate 24000 device cpu`.
If it fails, record the error type only. This is not a STOP condition for L1.

### L1.14 — Record versions and disk use
Working directory: any.
```bash
uv pip freeze --python "$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/python" | grep -i -E "^(pocket-tts|torch|huggingface)"
"$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/python" --version
sw_vers -productVersion
du -sm "$HF_HOME"
```
Record the values in `environment`.

### L1.15 — Write and check the result file
Working directory: `$TAMIL_TTS_REPO`.
```bash
cp docs/verification/TEMPLATE.yaml "docs/verification/pocket-tts-tamil-$(date +%F).yaml"
```
Fill in the file. Then check it:
```bash
.venv/bin/tamil-tts verify result "docs/verification/pocket-tts-tamil-$(date +%F).yaml"
```
Expected: `0 problem(s)`.
Commit only this YAML file. Never commit the WAV or log files.

## Part C — L2: IndicF5

Facts used here (VERIFIED, from the official IndicF5 README at commit
`13f7c4d627cc10111aea8fe9c0039462cacacdc7`):
- Install: Python 3.10, `pip install git+https://github.com/ai4bharat/IndicF5.git`.
- Interface: `AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)`, then
  `model(text, ref_audio_path=..., ref_text=...)`. Save with `samplerate=24000`.
- Three inputs are required: the text, a reference audio clip, and the exact transcript of that
  clip.
- The repository ships reference prompts in `prompts/`. Only `PAN_F_HAPPY_00001.wav` has a
  documented transcript (copied to `docs/verification/indicf5_ref_PAN_F_HAPPY_00001.txt`).
  `TAM_F_HAPPY_00001.wav` exists, but its transcript is **UNVERIFIED**. Do not use it until the
  transcript is found in an official source.
- `trust_remote_code=True` runs code from the Hugging Face repository. Pin the revision.

`scripts/verify/indicf5_smoke.py` wraps the README calls unchanged. It adds `revision=` and reads
the text from files, so the text is not in the process list.

Card URL: https://huggingface.co/ai4bharat/IndicF5

### L2.1 — Load the environment file
Working directory: any.
```bash
source "$HOME/.tamil-tts.env"
export V="$TAMIL_TTS_OUTPUT_ROOT/verification/indicf5/$(date +%F)"
mkdir -p "$V"
```

### L2.2 — Check the card
Do Part A for `ai4bharat/IndicF5`. Also read the discussion threads about the licence.
Expected: the licence (reported as MIT) is confirmed on the card. You have a full revision SHA.
Write the SHA into a variable:
```bash
export INDICF5_REVISION=<full 40-character SHA>
```
STOP if the licence is not MIT. Report it before you continue.

### L2.3 — Get the code and reference prompts at the pinned commit
Working directory: any.
```bash
git clone https://github.com/AI4Bharat/IndicF5 "$TAMIL_TTS_MODEL_ROOT/src/IndicF5"
git -C "$TAMIL_TTS_MODEL_ROOT/src/IndicF5" checkout 13f7c4d627cc10111aea8fe9c0039462cacacdc7
ls "$TAMIL_TTS_MODEL_ROOT/src/IndicF5/prompts"
```
Expected: the list includes `PAN_F_HAPPY_00001.wav`.

### L2.4 — Create the IndicF5 environment (Python 3.10)
Working directory: any.
```bash
uv venv --python 3.10 "$TAMIL_TTS_ENV_ROOT/indicf5"
```
Expected: `Creating virtual environment at: .../tamil-tts-envs/indicf5`.

### L2.5 — Install the pinned package
Working directory: any.
```bash
uv pip install --python "$TAMIL_TTS_ENV_ROOT/indicf5/bin/python" \
  "git+https://github.com/ai4bharat/IndicF5.git@13f7c4d627cc10111aea8fe9c0039462cacacdc7"
```
Expected: `Installed ... packages`, including `f5-tts`, `torch` and `transformers`.
STOP if the install fails. Copy the last error line.

### L2.6 — Run smoke test I1 (cold)
Working directory: `$TAMIL_TTS_REPO`.
This run downloads the model into `HF_HOME`.
```bash
cd "$TAMIL_TTS_REPO"
/usr/bin/time -l "$TAMIL_TTS_ENV_ROOT/indicf5/bin/python" scripts/verify/indicf5_smoke.py \
  --text-file docs/verification/smoke_text_ta.txt --line 1 \
  --ref-audio "$TAMIL_TTS_MODEL_ROOT/src/IndicF5/prompts/PAN_F_HAPPY_00001.wav" \
  --ref-text-file docs/verification/indicf5_ref_PAN_F_HAPPY_00001.txt \
  --revision "$INDICF5_REVISION" \
  --out "$V/i1_cold.wav" > "$V/i1_cold.json" 2> "$V/i1_cold.log"
cat "$V/i1_cold.json"
```
Expected: JSON with `load_s`, `generate_s`, `duration_s` and `rtf_generate`.
STOP if the JSON contains `"error"`. Look at the last lines of `$V/i1_cold.log`. If you see
`401`, `403` or `GatedRepo`, do step A5 and repeat. Otherwise copy only the last error line.

### L2.7 — Run smoke test I1 again (warm, offline)
Working directory: `$TAMIL_TTS_REPO`.
```bash
HF_HUB_OFFLINE=1 /usr/bin/time -l "$TAMIL_TTS_ENV_ROOT/indicf5/bin/python" scripts/verify/indicf5_smoke.py \
  --text-file docs/verification/smoke_text_ta.txt --line 1 \
  --ref-audio "$TAMIL_TTS_MODEL_ROOT/src/IndicF5/prompts/PAN_F_HAPPY_00001.wav" \
  --ref-text-file docs/verification/indicf5_ref_PAN_F_HAPPY_00001.txt \
  --revision "$INDICF5_REVISION" \
  --out "$V/i1_warm.wav" > "$V/i1_warm.json" 2> "$V/i1_warm.log"
cat "$V/i1_warm.json"
grep -E " real |maximum resident set size" "$V/i1_warm.log"
```
Expected: the same JSON fields. Record `warm_elapsed_s` (`real`), `peak_rss_bytes`, and
`generate_s` in the notes.
If it fails with an offline error, run it again without `HF_HUB_OFFLINE=1`. Record "offline: no".

### L2.8 — Inspect the audio
Working directory: `$TAMIL_TTS_REPO`.
```bash
.venv/bin/tamil-tts audio inspect "$V/i1_warm.wav" --elapsed <generate_s from i1_warm.json>
```
Expected: `"status": "ok"`, `"sample_rate": 24000`, `"channels": 1`.
Record `output_duration_s`, `real_time_factor` and `audio_check`.
STOP if the status is `silent`, `empty` or `invalid`.

### L2.9 — Listen
Working directory: any.
```bash
afplay "$V/i1_warm.wav"
```
Record `listening.all_words_spoken`, `listening.intelligible` and notes. The reference voice is a
Punjabi speaker, so expect a non-Tamil voice quality. Note it, but do not fail the test for it.

### L2.10 — Optional: smoke tests I2 and I3
Repeat L2.7 to L2.9 with `--line 2` and `--line 3`, and new output names.

### L2.11 — Record versions and disk use
Working directory: any.
```bash
uv pip freeze --python "$TAMIL_TTS_ENV_ROOT/indicf5/bin/python" | grep -i -E "^(f5-tts|f5_tts|torch|torchaudio|transformers|numpy|vocos)"
"$TAMIL_TTS_ENV_ROOT/indicf5/bin/python" --version
du -sm "$HF_HOME"
```
Record the values in `environment`.

### L2.12 — Write and check the result file
Do the same as L1.15, with the file name `indicf5-<date>.yaml` and `model: indicf5`.

Not part of L2 (UNVERIFIED, later): running on the Apple GPU (`mps`), and the `TAM_F_HAPPY_00001`
prompt.

## Part D — Information needed to implement each subprocess adapter

C6 implements an adapter only when every row below has a recorded, verified value.

| Item | Why it is needed | Pocket TTS Tamil (known now) | IndicF5 (known now) |
|---|---|---|---|
| Python executable | The adapter starts it as a subprocess | `$TAMIL_TTS_ENV_ROOT/pocket-tts/bin/python` (planned) | `$TAMIL_TTS_ENV_ROOT/indicf5/bin/python` (planned) |
| Invocation | Exact verified command or call | CLI `pocket-tts generate --config ... --text ... --output-path ...` (VERIFIED). Python API with `hf://` config: UNVERIFIED (L1.13) | `AutoModel.from_pretrained(..., trust_remote_code=True)` + `model(text, ref_audio_path, ref_text)` (VERIFIED) |
| Text input channel | Keep text out of the process list and logs | CLI: argv only (`--text`). A worker would use stdin or a file | Python argument. The worker reads a file or stdin |
| Load once or per segment | Model load time decides worker design | Measure: compare cold vs warm `real` with load time | `load_s` vs `generate_s` from the script |
| Reference audio | Request validation, cache key | Voice audio only, no transcript (VERIFIED) | Audio + exact transcript (VERIFIED) |
| Output format | Completeness checks, sample-rate handling | WAV 24 kHz mono PCM16 (VERIFIED) | 24 kHz. Container and sample format from `audio inspect` |
| Pinned versions | Cache key (`ModelIdentity.version`) and reproducibility | `pocket-tts==4.0.1`, config `@80c7f283…` | Git `13f7c4d6…`, HF revision from L2.2 |
| Device | Runtime metadata | `cpu` (default) | Default device as observed. `mps` UNVERIFIED |
| Offline behaviour | PRD offline requirement | L1.9 result | L2.7 result |
| Failure signatures | Map to `ErrorCode` values | Gated or 401/403, missing weights, non-zero exit | Same, plus Python exceptions in the JSON `error` field |
| Timeouts | Prevent hung runs | Use warm elapsed per sentence × safety factor (TBD) | Same |
| Peak memory | `RuntimeMetadata.peak_memory_bytes` | `/usr/bin/time -l` | `/usr/bin/time -l` |
| Licence conditions | Decide what the outputs may be used for | CC BY 4.0 (confirm). Prohibited-use terms | MIT (confirm) |

## Part E — Safe error handling

Model errors can repeat their input. A Tamil sentence or a private path in an error message would
leak private data into result files that are meant to be committed.

Rules for adapters and verification:
1. Pass text to a model by file or stdin, not on the command line, wherever the interface allows
   it. (Pocket's CLI only accepts `--text`; this is acceptable for the original smoke sentences.
   It is not acceptable for TAM text.)
2. Never copy raw stderr or tracebacks into `results.json`, `errors.jsonl` or `REPORT.md`. Keep
   raw logs only in the run folder under `$TAMIL_TTS_OUTPUT_ROOT`, outside Git.
3. Map failures to the fixed error codes: `unavailable`, `invalid_request`,
   `unsupported_reference`, `runtime_error`, `incomplete_output`.
4. Pass every message through `tamil_tts.models.errors.sanitize_message`. It removes the request
   text, the reference transcript, the request paths, any Tamil-script text and absolute paths,
   then truncates to 300 characters. `BaseTTSModel` already does this for exceptions.
5. In verification result files, describe problems by word position (for example "word 3 is
   skipped"), not by quoting private text. Quoting the original smoke sentences is allowed.
6. Never paste full logs into chat or into Claude's context. Copy the last error line only.

## Sources

- Pocket TTS README and CLI reference: https://github.com/kyutai-labs/pocket-tts (commit
  `44cb63eaa4144f32ff80863968515165a5554353`), `docs/CLI Commands/generate.md`,
  `docs/API Reference/python-api.md`
- pocket-tts on PyPI: https://pypi.org/project/pocket-tts/ (4.0.1)
- IndicF5 README and `setup.py`: https://github.com/AI4Bharat/IndicF5 (commit
  `13f7c4d627cc10111aea8fe9c0039462cacacdc7`)
- uv installation: https://docs.astral.sh/uv/getting-started/installation/
