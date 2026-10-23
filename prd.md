Implementation handoff • Verified Tamil text → accessible speech • Cloud engineering / local model execution • Model strategy: Pocket TTS + IndicF5 + Indic-Speak
Mission: use Claude Code Cloud for as much software engineering, experiment orchestration, analysis and reporting as possible, while keeping Tamil recordings, TTS models, generated audio, checkpoints, inference and fine-tuning on the user's MacBook Pro M4 Max. The product outcome is a reproducible Tamil speech pipeline that demonstrably improves previously difficult-to-understand TTS passages for elderly and visually impaired listeners.
1. Operating model
Responsibility
Claude Code Cloud
Local M4 Max
Code
Design, implement, refactor, test
Pull and execute
Tamil front end
Implement normalization/segmentation/lexicon
Run against real text
Models
Adapters/configs; never assume APIs
Install/run Pocket TTS, IndicF5, later candidates
TAM corpus
Manifest/schema/validation logic
Raw WAV recordings remain local
Inference
Prepare runner/config
Generate WAV/audio
Fine-tuning
Prepare scripts/configs/guards
Perform compute-heavy tuning
Evaluation
Implement metrics/reporting
Run ASR/audio checks + human listening
Results
Analyze compact JSON/JSONL/Markdown
Commit compact results only
Artifacts
Code/configs/reports
Weights, checkpoints, audio, caches
2. Architectural principle: Git is the control plane
Git carries instructions, code and compact evidence. It does not carry the model/audio workload.
Committed: source code, tests, manifests without private binary audio, experiment plans/configs, normalization rules, pronunciation lexicon metadata, metrics, error annotations, concise reports.
Local only: TAM WAV files, model weights, checkpoints, generated WAV/MP3, Automatic Speech Recognition (ASR) caches, large intermediate datasets.
Every experiment is reproducible from a committed config plus documented local environment/model identifiers.
Claude must reason from structured metrics/errors, not require audio binaries in its context.
3. Target architecture
GitHub repository (control plane)
│
├──────────────► Claude Code Cloud
│ code / tests / experiment plans
│ analyze results / propose next change
│
▼
Local MacBook Pro M4 Max
tamil-tts experiment run EXP-xxx
│
├─ load local TAM audio
├─ load local TTS model
├─ synthesize/cache audio
├─ completeness + ASR checks
├─ human listening UI
└─ write compact result artifacts
│
└────► commit results.json, errors.jsonl, REPORT.md
│
└────► Claude Code Cloud
4. Product scope and non-goals
Input is already-correct Tamil text. OCR correction is outside this PRD.
V1 does not train a TTS model from scratch.
V1 benchmarks three first-class candidates: Pocket TTS Tamil, IndicF5, and Indic-Speak. They share one adapter/evaluation contract but serve different product roles.
Indic-Speak is a first-class audiobook-quality candidate. Its adapter must gracefully report unavailable/unsupported when the released code, weights, license, or local runtime are not yet usable; Claude must verify the actual current implementation rather than infer APIs from announcements.
Do not build a hosted production service, mobile app, user accounts or cloud audio store in V1.
Do not optimize for generic 'human-like' speech at the expense of intelligibility, completeness or listening comfort.
4A. Three-model product strategy
Use all three models initially; do not force one model to satisfy every product need.
Pocket TTS Tamil — deployment-efficiency benchmark: small/offline/CPU-friendly. Goal: determine whether a lightweight model can become sufficiently intelligible for accessible local reading.
IndicF5 — adaptation laboratory: supports reference-audio conditioning, making TAM-xxx recordings directly useful before fine-tuning. Goal: measure how much Tamil pronunciation/prosody improves through carefully selected TAM reference prompts and later targeted adaptation.
Indic-Speak — audiobook-quality / long-form benchmark and potential production model: prioritize evaluation of literary Tamil, mixed Tamil-English/script text, voice consistency, and sustained listening. Treat its September 2026 release as newer but do not assume it wins; measure it on the same frozen benchmark.
The eventual product may intentionally use more than one model: e.g., Indic-Speak for master audiobook generation, Pocket TTS for lightweight offline reading, and IndicF5 for TAM-conditioned or personalized/adaptation experiments.
5. User and outcome
Primary users: visually impaired Tamil listeners and elderly Tamil listeners consuming books/guides for sustained periods. Secondary users: volunteers/reviewers producing and validating accessible audio.
V1 outcome: at least one offline-capable pipeline reads frozen difficult Tamil passages with zero silent omissions, materially fewer adjudicated pronunciation errors than baseline, no meaningful frozen-set regression, and acceptable sustained-listening comfort.
6. Repository contract
tamil-accessible-tts/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .gitignore
├── configs/
│ ├── models.yaml
│ ├── eval.yaml
│ └── release_gates.yaml
├── data/
│ ├── manifests/tam.jsonl
│ └── text/{smoke,test,challenge}/
├── lexicon/
│ ├── pronunciation.jsonl
│ └── proper_names.jsonl
├── src/tamil_tts/
│ ├── frontend/{normalize.py,segment.py,numbers.py,lexicon.py}
│ ├── models/{base.py,pocket.py,indicf5.py,indicspeak.py}
│ ├── eval/{completeness.py,asr.py,metrics.py,report.py}
│ ├── listening/app.py
│ └── cli.py
├── tests/{unit,regression}/
├── experiments/
│ ├── EXP-001/{PLAN.md,config.yaml}
│ └── ...
├── scripts/run_local.sh
└── .local/ # NEVER COMMIT
├── datasets/tam/audio/
├── models/
├── checkpoints/
├── audio/
└── cache/
7. Local data and environment contract
Committed manifests reference logical roots, not personal absolute paths.
{"id":"TAM-001","split":"train","text":"<Tamil>","audio":"${TAM_AUDIO_ROOT}/TAM-001.wav","speaker_id":"SPK-01","tags":["literary","PHON-LIQUID"],"quality":"accepted"}
Local environment example:
export TAM_AUDIO_ROOT="$HOME/tamil-tts-data/tam/audio"
export TAMIL_TTS_MODEL_ROOT="$HOME/tamil-tts-models"
export TAMIL_TTS_CACHE_ROOT="$HOME/tamil-tts-cache"
Secrets and personal paths are never committed.
Runner fails clearly when required local roots/models are absent.
Model adapter exposes capability/status checks so Claude-written code can be tested without pretending the model exists in cloud.
8. TAM dataset split and protection
Split
Target
Train?
Rule
TRAIN
~70%
Yes
Adaptation data
VALIDATE
~10%
Validation only
Model/checkpoint selection
TEST
~10%
Never
Frozen after EXP-001
CHALLENGE
~10%
Never
Hard phonology + real difficult book prose
Split by speaker where feasible; remove duplicate/near-duplicate text leakage. At least half of CHALLENGE duration should be natural literary/book prose. New failures discovered after freeze enter a versioned future challenge set, not TRAIN.
9. Tamil linguistic taxonomy
Tag
Coverage
PHON-LIQUID
ல / ள / ழ
PHON-RHOTIC
ர / ற / ற்ற
PHON-NASAL
ந / ன / ண / ங / ஞ
PHON-VOWEL
short/long vowels; ஐ / ஔ
PHON-GEM
consonant doubling
SCRIPT-GRANTHA
ஜ / ஷ / ஸ / ஹ and loanwords
PROSODY
clauses, punctuation, dialogue, long literary sentences
NORM-NUM
numbers, dates, currency, percentages, units
MIXED
Tamil + English, names, abbreviations
LITERARY
older/literary Tamil and target-book vocabulary
ACCESS
pace, pauses, clarity and listening fatigue
10. Tamil speech front end
Preserve source_text, normalized_text and segment_text separately.
Unicode normalization is deterministic and auditable.
Expand numbers/dates/currency/units via explicit rules.
Pronunciation overrides come from a versioned lexicon with provenance.
Segment at sentence boundaries; split long clauses only at safe punctuation/configured thresholds.
Every segment has immutable segment_id, source offsets, checksum and expected text length.
No residual text may disappear during segmentation.
Front-end fixes are preferred over model tuning for deterministic textual problems.
11. Common model adapter
Cloud code must never embed model-specific logic throughout the product. Implement a stable interface conceptually equivalent to:
class TTSModel(Protocol):
def status(self) -> ModelStatus: ...
def synthesize(self, text: str, output_path: Path, **opts) -> SynthesisResult: ...
def version_info(self) -> dict: ...
def supports_reference_audio(self) -> bool: ...
Pocket TTS, IndicF5, and Indic-Speak implement this interface. If a cloud environment lacks a model/runtime, adapter tests use mocks/stubs. For Indic-Speak especially, Claude must inspect the currently released authoritative code/model documentation and implement only verified interfaces; an unavailable adapter is preferable to an invented API.
12. Local experiment runner — primary interface
The stable interface is the Python command, not shell implementation details:
tamil-tts experiment run EXP-001
tamil-tts experiment run EXP-001 --smoke
tamil-tts experiment status EXP-001
tamil-tts listen EXP-001
tamil-tts eval report EXP-001
tamil-tts compare EXP-001 EXP-002
tamil-tts release-check EXP-004
scripts/run_local.sh may activate the environment and call the CLI, but experiment semantics live in tested Python code.
13. Local runner behavior
validate config + manifest
→ resolve local roots
→ verify model availability/version
→ normalize + segment
→ hash model/config/text
→ reuse cached synthesis when hash matches
→ synthesize missing segments
→ verify every segment produced audio
→ run duration/silence sanity checks
→ optional local ASR comparison
→ write metrics.json
→ write errors.jsonl
→ generate REPORT.md
→ NEVER commit audio automatically
14. Experiment ladder
ID
Change
Training
Decision
EXP-001
Frozen baseline: Pocket TTS, IndicF5 standard reference, IndicF5 + selected TAM reference, Indic-Speak
No
Compare deployment efficiency, reference conditioning, and newer audiobook/long-form quality on identical text
EXP-002
Apply Tamil normalization, segmentation and lexicon to all available model paths
No
Separate language-engineering gains from model gains
EXP-003
Systematic IndicF5 TAM reference-prompt study; compare best result with Indic-Speak
No
Find robust TAM reference prompts and determine remaining model-specific errors
EXP-004
Targeted adaptation/fine-tuning: IndicF5/Pocket first; Indic-Speak only if verified released tooling supports it
Yes
Tune only persistent acoustic/pronunciation failures that survived EXP-001..003
EXP-005
Additional TAM recordings targeted to persistent cross-model or model-specific error clusters
Yes
Add data only where measured failures justify it
EXP-004 is blocked until EXP-001 through EXP-003 have committed evidence and remaining errors are repeatable, linguistically clustered, and not adequately fixed by the speech front end/reference conditioning.
15. Evaluation and compact result contract
Each experiment commits only compact evidence. Minimum files:
experiments/EXP-001/
PLAN.md
config.yaml
results.json
errors.jsonl
listener_results.jsonl # when human evaluation exists
REPORT.md
errors.jsonl example:
{"id":"TAM-037","segment_id":"TAM-037-S01","model":"pocket-v0","category":"PHON-LIQUID","word":"வாழ்க்கை","asr_output":"...","human_error":true,"severity":3,"notes":""}
16. Metrics and release gates
Metric
Initial target
Role
Completeness
100%; 0 missing/silent segments
Hard gate
Frozen regression
No material regression
Hard gate
Pronunciation errors
≥30% reduction vs selected baseline
Quality target; recalibrate after EXP-001
Challenge intelligibility
≥90%
Human authoritative
Comfort
Median ≥4/5 and not below baseline
Accessibility
Real-time factor
Measure/report
Deployment
Peak memory
Measure/report
Deployment
Do not collapse these into one composite score. Better naturalness cannot compensate for omitted text.
17. Human listening interface
`tamil-tts listen EXP-xxx` launches a small local-only browser interface.
Blind/randomized A/B where possible; audio paths remain local.
Capture: clearer A/B/same, pronunciation error category, problem word, optional notes, comfort 1–5.
Test intelligibility without showing text; separately test pronunciation with text visible.
Include 5–10 minute sustained listening for comfort/fatigue; later add ~15-minute chapter validation.
Write structured listener_results.jsonl for Claude to analyze; never require Claude to ingest audio.
18. Fine-tuning contract
Claude Cloud prepares dataset transforms, training scripts, configs, validation logic and checkpoint evaluation for models whose current released tooling supports adaptation. Do not assume Indic-Speak fine-tuning support; verify its current code/license/runtime first.
Local M4 executes training/adaptation and stores checkpoints under .local/checkpoints/.
TRAIN only supplies gradient updates. VALIDATE selects. TEST/CHALLENGE never participate in training.
Prefer parameter-efficient adaptation when supported and evidence warrants it.
Keep baseline + best + last checkpoints unless a model-specific reason requires more.
Additional TAM recordings are selected from persistent error clusters, not arbitrary recording-hour targets.
19. Token-efficiency requirements for Claude Code Cloud
`AGENTS.md` is the standing contract and should stay ≤150 lines.
Each experiment has a compact PLAN.md containing only objective, inputs, allowed scope, commands, gates and outputs.
Claude reads only AGENTS.md + current PLAN.md + files necessary to implement the current task.
Previous experiments are consumed from results.json/errors.jsonl, not long chat summaries.
Use a 12–20 utterance smoke set during coding; full frozen evaluation runs only at experiment checkpoints.
Cache synthesis and ASR by model/config/text checksum; unchanged samples are never regenerated.
Do not upload/paste WAV files, checkpoints or verbose logs into Claude context.
Store machine-readable results; generate reports programmatically.
Claude response after implementation: changed files; tests; exact local command; expected outputs; blockers. No project-history recap.
One concern per prompt when debugging. Give Claude the failing command + compact error excerpt + relevant file path, not entire logs.
20. AGENTS.md — bootstrap content
# Tamil Accessible TTS — Claude Cloud Contract
GOAL
Improve verified Tamil text → accessible offline speech, measured on frozen TAM evaluation data.
BOUNDARY
Cloud: code/tests/configs/analysis. Local M4: models/audio/inference/training/listening.
NON-NEGOTIABLE
Never alter source Tamil text.
Never train on TEST or CHALLENGE.
Never change frozen split membership after EXP-001.
Preserve source_text and normalized_text separately.
Every segment is traceable by immutable ID/checksum.
Zero missing/silent text is a hard release gate.
Human Tamil judgments outrank ASR for pronunciation.
Prefer deterministic front-end fixes over tuning when appropriate.
Do not start EXP-004 until EXP-001..003 gates are complete.
Never invent model APIs; verify authoritative docs/source.
Never require raw audio/model weights in cloud context.
Do not overwrite experiment outputs.
Treat Pocket TTS, IndicF5 and Indic-Speak as first-class evaluation candidates.
IndicF5 TAM reference prompting is required before IndicF5 fine-tuning.
For Indic-Speak, verify current released code/API/license/local feasibility; never infer an interface from an announcement.
WORK STYLE
Read current experiment PLAN.md and only relevant files.
Plan <=8 bullets; implement; test.
Use mocks when cloud lacks local models.
Use smoke set while coding.
Save JSON/JSONL metrics and concise Markdown reports.
End with: changed files; tests; local command; expected result files; blockers/next decision.
21. EXP-001 PLAN.md — bootstrap content
# EXP-001 — Frozen Baseline
OBJECTIVE
Measure Pocket TTS Tamil, IndicF5 (standard + selected TAM reference), and Indic-Speak on the same frozen Tamil benchmark before any tuning.
INPUTS
data/manifests/tam.jsonl
smoke/test/challenge text
local model roots via environment variables
CLOUD DELIVERABLES
manifest validator + frozen split guard
Tamil segment pipeline preserving source text
common TTS adapter
Pocket + IndicF5 + Indic-Speak adapters (Indic-Speak may report unavailable if verified local tooling is not usable)
cache/checksum layer
completeness/duration/silence checks
optional ASR adapter
result/report generator
local listening UI
unit/regression tests
LOCAL RUN
tamil-tts experiment run EXP-001 --smoke
then:
tamil-tts experiment run EXP-001
OUTPUTS TO COMMIT
results.json
errors.jsonl
REPORT.md
DO NOT
fine-tune; build production UI; add database; commit audio; change source Tamil.
22. Exact first prompt to Claude Code Cloud
Read AGENTS.md and experiments/EXP-001/PLAN.md.
Implement EXP-001 and only the reusable infrastructure required by that plan.
Important environment assumption:
You are the cloud engineering agent.
TTS models, TAM WAV files, generated audio, checkpoints and compute-heavy inference exist only on my local MacBook Pro M4 Max.
EXP-001 candidates are Pocket TTS Tamil, IndicF5 (including selected TAM reference-audio conditioning), and Indic-Speak.
Your code must therefore be fully testable with mocks/stubs in cloud and executable against real models locally.
Do not require model/audio binaries in your context.
Never guess a model API; verify the currently supported interface from authoritative source/documentation before implementing its adapter.
Indic-Speak is a first-class candidate, but if its current released code/weights/runtime are unavailable or incompatible locally, implement a clean capability check/stub and document the blocker rather than fabricating support.
Before coding: give a plan of at most 8 bullets.
Then implement and test.
At completion return only:
files changed
tests/commands run in cloud
the exact local setup/run commands I should execute on my Mac
result files I should commit back
blockers, if any
Do not fine-tune anything in EXP-001.
23. Local execution feedback prompt
After running EXP-001 locally and committing the compact result files, use:
Read AGENTS.md, experiments/EXP-001/PLAN.md, results.json, errors.jsonl and REPORT.md.
Do not inspect unrelated repository files.
Analyze the baseline by Tamil linguistic category and model, explicitly comparing Pocket TTS, IndicF5 standard reference, IndicF5 + TAM reference, and Indic-Speak when available.
Identify:
text-loss/completeness failures
deterministic normalization/segmentation failures
pronunciation clusters
problems likely addressable by reference prompting
problems that may eventually require adaptation
Create experiments/EXP-002/PLAN.md and implement EXP-002 only.
Do not fine-tune.
Return changed files, tests, exact local command, expected result files, and the decision criteria for EXP-003.
23A. Model selection is role-based, not winner-take-all
After EXP-001..003, retain multiple models if they serve distinct needs. Compare at minimum: pronunciation by Tamil taxonomy, completeness, mixed-script handling, long-form consistency, listener comfort, real-time factor, memory, local/offline feasibility, reference-audio benefit, and verified adaptation path.
Do not label the newest model as best without frozen-set evidence. Indic-Speak's newer release makes it important to test, not automatically superior.
A valid V1 outcome may be a portfolio: Indic-Speak for high-quality audiobook production, Pocket TTS for compact offline access, and IndicF5 for TAM-conditioned/adapted speech.
24. Definition of done
V1 is done when the repository can reproducibly orchestrate local Tamil TTS experiments from Claude-authored code/configs, preserve frozen evaluation integrity, produce structured evidence without uploading audio to Claude, and deliver at least one offline-capable candidate that passes completeness/regression gates and demonstrates meaningful pronunciation/intelligibility improvement on previously difficult Tamil passages.