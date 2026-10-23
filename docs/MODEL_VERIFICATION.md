# Model Verification

Status of the three evaluation candidates (PRD §4A, §11). Researched 2026-10-23 from Claude Code
Cloud. Licences updated 2026-10-23 (C4) with the user's findings, each checked
against what could be reached from the cloud. **No model is verified for implementation yet.** Every adapter stays a placeholder that
reports `unverified` (`tamil-tts models status`) until the open checks below are closed on the
local Mac.

## How to read this document

| Label | Meaning |
|---|---|
| **Confirmed** | Read directly from the official source (GitHub repository, PyPI) at the commit listed |
| **Reported** | Seen only through search results quoting the Hugging Face card, or a secondary source. Must be confirmed on the card itself |
| **Not found** | No official statement located |

`huggingface.co` is blocked by this cloud environment's network policy, so no Hugging Face model
card could be opened directly. Every Hugging Face claim below is therefore **Reported**. Nothing
was downloaded.

## Summary

| | Pocket TTS Tamil | IndicF5 | Indic-Speak |
|---|---|---|---|
| Official source | Engine: `kyutai-labs/pocket-tts` (Confirmed). Tamil weights: **community** model `Thanushttk/pocket-tts-multilingual`, listed in the official README (Confirmed) | `AI4Bharat/IndicF5` (GitHub) + `ai4bharat/IndicF5` (HF) (Confirmed) | Code: `Bodhan-AI/bodhan_genai` (`bodhan_genai.tts`) (Confirmed). Weights: `bodhan-ai/indic-speak` (HF) (Confirmed as default checkpoint) |
| Licence | Weights: **CC BY 4.0** (user finding; Reported). The card says the bundled Kyutai weights are used under CC-BY-4.0. The repo's own licence tag could not be read from the cloud. Engine code MIT (Confirmed). Upstream prohibited-use terms apply, including cloning a voice without explicit, lawful consent (Confirmed) | **MIT** (user finding; Reported). Consistent with AIKosh and community derivatives. GitHub repo has **no LICENSE file** (Confirmed). An HF discussion "confirming the MIT grant for commercial use" exists; its outcome is unread | Weights: **Indic Open Model License v1.0** (user finding; Reported from the model card). Gated. Derivatives must carry the same licence. Hosted third-party APIs need written approval. Llama 3.2 upstream terms may also apply. Code Apache-2.0 (Confirmed) |
| Version | `pocket-tts` 4.0.1 on PyPI; repo `44cb63eaa414`. Tamil config pinned at HF commit `80c7f2835138…` (Confirmed) | No releases; repo `13f7c4d627cc` (Confirmed). HF revision: Not found | `bodhan_genai` 0.1.0, repo `62090c5e8f77` (Confirmed). Weights revision: Not found |
| Tamil support | Yes, in the community 6-layer multilingual model (en, hi, mr, kn, ta, ml, te, code-mixing) (Confirmed). Not in the official Kyutai language list (Confirmed) | Yes, 1 of 11 languages (Confirmed) | Yes, `ta`. Production tier (Reported). Content-fidelity judge score 4.904 on 3,000 readings (Confirmed, package README) |
| Reference audio | Voice prompt via `get_state_for_audio_prompt(path)` (WAV). No transcript needed. Duration not specified (Confirmed). Official cloning weights are gated on HF (Reported) | **Required**: reference WAV + its transcript per call (Confirmed). Length/format limits: Not found | **Not supported**. Fixed speakers selected by name (Reported: "does not support voice cloning"; package README shows `speaker=` only) |
| Local inference | Python 3.10–3.14, PyTorch ≥ 2.5, CPU. `pip install pocket-tts` (Confirmed) | Python 3.10 (conda), `pip install git+https://github.com/ai4bharat/IndicF5.git`. Loads with `trust_remote_code=True` (Confirmed) | Python 3.12, vLLM backend (default) or `backend="hf"`. CUDA wheels by default; `--cpu` dev install exists. ~3.4–3.8B params (Confirmed / Reported) |
| Apple Silicon | ~6× real time on a MacBook Air M4 CPU. No GPU speed-up observed on Apple Silicon. No MPS support mentioned (Confirmed) | Not documented officially. Community MLX port and ONNX export exist (Reported, unofficial). ONNX export "not realtime on M1 CPU" (Reported) | **Not documented**. Only CUDA is referenced. vLLM is CUDA-oriented. The HF backend on MPS/CPU is untested |
| Inference interface | `TTSModel.load_model()` → `get_state_for_audio_prompt(voice)` → `generate_audio(state, text)` → 1-D torch tensor at `tts_model.sample_rate`. CLI: `pocket-tts generate --config hf://…/config.yaml@<sha> --voice v.wav --text …` (Confirmed for the official model; community model via `--config` per README) | `AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)`, called with text, ref audio path and ref text. Returns int16 audio at 24 kHz (Confirmed, README) | `IndicTTSEngine(checkpoint).synthesize(text, speaker=..., style="")` → `TTSResult` (float32, 24 kHz, `.save(path)`, `rtf`, `duration_s`). Long-form: `ChunkedIndicStreamingTTS` (Confirmed, package README) |

## Licence findings (C4)

| Model | User finding | Check result | Still to confirm on the card |
|---|---|---|---|
| Pocket multilingual Tamil weights | CC BY 4.0 | Supported: the card states CC-BY-4.0 for the bundled Kyutai weights, and upstream Kyutai weights are CC-BY-4.0 | The repo's own `license:` tag and attribution wording |
| IndicF5 | MIT | Consistent across secondary sources, but not read from the card itself | The `license:` field on `ai4bharat/IndicF5`, plus any voice-cloning terms of use |
| Indic-Speak weights | Indic Open Model License v1.0 | Supported: search results quote it from the model card | Full licence text (commercial use, attribution, hosting) after accepting the gate |

These are recorded as licence findings only. **Local model execution is not verified for any
model**, and `verified` stays `false` in `configs/models.yaml`.

## Pocket TTS Tamil

- **What it is:** Kyutai's Pocket TTS engine running a **community-trained** multilingual
  checkpoint by Thanush Thankachan, linked from the official README's community-models list. It
  is not an official Kyutai Tamil model.
- **Sources:** https://github.com/kyutai-labs/pocket-tts ·
  https://huggingface.co/Thanushttk/pocket-tts-multilingual (Reported: ~418 MB, CPU-oriented,
  voice cloning from a short WAV).
- **Known limitations:**
  - Pauses cannot be inserted via text (upstream issue #6).
  - GPU is not officially supported.
  - Prebuilt voices are not available for community models; a reference voice is needed.
  - The Rust binary is not bit-identical to Python output.
- **Open checks:**
  - Licence of the Tamil weights.
  - Training-data provenance.
  - Whether the `hf://` config path works with `pocket-tts` 4.0.1.
  - Output sample rate (read from `tts_model.sample_rate`).
  - Behaviour with Tamil-only text.

## IndicF5

- **Sources:** https://github.com/AI4Bharat/IndicF5 · https://huggingface.co/ai4bharat/IndicF5.
- **Facts:** Built on F5-TTS. Trained on 1,417 h (Rasa, IndicTTS, LIMMITS, IndicVoices-R).
  Output is 24 kHz. Every call needs reference audio and its exact transcript, which makes it the
  natural home for TAM reference prompts (PRD §4A).
- **Known limitations:**
  - `trust_remote_code=True` executes code from the model repo. Pin a reviewed revision.
  - Python 3.10 differs from this project's 3.11 target.
  - The official HF Space showed a runtime error when indexed (Reported).
- **Open checks:**
  - Licence on the HF card (MIT is reported only secondhand; no LICENSE file in the repo).
  - Whether the HF repo is gated.
  - Reference-clip length limits.
  - PyTorch MPS vs CPU on the M4 Max.
  - Pinned HF revision.

## Indic-Speak

- **Sources:** https://github.com/Bodhan-AI/bodhan_genai (`src/bodhan_genai/tts/README.md`) ·
  https://huggingface.co/bodhan-ai/indic-speak. Released September 2026 by Bodhan AI.
- **Facts:**
  - Llama-3.2-3B backbone → SNAC 24 kHz tokens → fine-tuned Vocos decoder.
  - Single-shot generation caps at about 25 s; longer text needs the chunked classes.
  - The offline (Vocos) and streaming (stock SNAC) paths are not bit-identical.
  - Published evaluation covers content fidelity only, not naturalness or prosody.
  - LoRA and full fine-tuning configs exist (training needs flash-attn).
- **Known limitations:**
  - CUDA/vLLM-centred stack; Apple Silicon is unverified and may be infeasible at useful speed.
  - Python 3.12 differs from this project's 3.11 target.
  - No voice cloning, so TAM recordings cannot condition it.
  - Gated licence with hosting restrictions.
  - Tamil speaker names differ between sources (Anitha/Arun on the card vs `tamil_female_ananya`
    in a community mirror) (Reported).
- **Open checks:**
  - Full licence text and gating terms.
  - Exact Tamil speaker IDs.
  - Whether `backend="hf"` runs on MPS or CPU on the M4 Max, and how fast.
  - Memory use in bf16.
  - Pinned weights revision.
- If it cannot run locally, its adapter stays `unavailable` with that reason (PRD §4).

## Consequences for the design

1. **Separate runtimes:** the candidates need Python 3.10 (IndicF5), 3.10–3.14 (Pocket) and 3.12
   (Indic-Speak). This project targets 3.11. Real adapters will likely have to call each model in
   its own local environment (for example a subprocess per model venv) rather than import it.
   **OPEN QUESTION** for C4. The `TTSModel` interface already allows either approach.
2. **Reference audio:** only IndicF5 requires reference audio plus transcript. Pocket TTS takes
   audio only, and Indic-Speak takes none. The interface carries an optional reference with
   transcript and checksum, and adapters declare support through `supports_reference_audio()`.
3. **Sample rates:** IndicF5 and Indic-Speak output 24 kHz; Pocket's rate is read at run time.
   Evaluation must not assume a single sample rate.

## Verification checklist (local Mac, before writing each real adapter)

The detailed, step-by-step procedure is in
[MODEL_VERIFICATION_CHECKLIST.md](MODEL_VERIFICATION_CHECKLIST.md) (C5). Summary:

1. Open the Hugging Face card and record the licence, gating terms and pinned revision (commit
   SHA) in `configs/models.yaml`.
2. Confirm the licence allows the intended use: evaluation, adaptation and distribution of
   generated audio.
3. Install in an isolated environment. Record Python, torch and package versions.
4. Run the documented example with **non-TAM, non-private text** and confirm the documented
   interface matches.
5. Record the device used (CPU/MPS), real-time factor and peak memory.
6. Only then set `verified: true` and write the adapter against the confirmed interface.

## Sources

- https://github.com/kyutai-labs/pocket-tts (README, LICENSE; commit `44cb63eaa414`)
- https://pypi.org/project/pocket-tts/ (4.0.1, requires Python ≥3.10,<3.15)
- https://huggingface.co/Thanushttk/pocket-tts-multilingual (via search only)
- https://huggingface.co/kyutai/pocket-tts (via search only)
- https://github.com/AI4Bharat/IndicF5 (README; commit `13f7c4d627cc`)
- https://huggingface.co/ai4bharat/IndicF5 (via search only)
- https://aikosh.indiaai.gov.in/home/models/details/aibharat_indicf5.html (licence, secondary)
- https://huggingface.co/yogenghodke/indic-f5-mlx, https://huggingface.co/developerabu/IndicF5-ONNX (community ports)
- https://github.com/Bodhan-AI/bodhan_genai (README, `src/bodhan_genai/tts/README.md`, LICENSE; commit `62090c5e8f77`)
- https://huggingface.co/bodhan-ai/indic-speak (via search only)
- https://www.analyticsvidhya.com/blog/2026/09/bodhan-ai-indic-models/ (release coverage)
