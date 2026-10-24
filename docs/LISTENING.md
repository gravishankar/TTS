# Listening and Human Evaluation (EXP-001)

`tamil-tts listen` is a small local web page for rating synthesized Tamil segments
(PRD §17). It runs on the Mac, binds to `127.0.0.1` only, and loads nothing from the
internet.

## Modes (PRD §17)

| Mode | While rating | After the rating is saved | Collected |
|---|---|---|---|
| `blind` (blind listening) | Model identity and Tamil text are hidden | Identity is revealed, plus the text if a manifest was given. The rating is then **final** | Perceived intelligibility (yes / no / unsure), naturalness (1–5), listening comfort (1–5) |
| `text` (text-assisted verification) | Tamil reference text shown (authorized reviewers, private manifest); model identity hidden | Identity is revealed. Re-rating adds a new revision | Pronunciation accuracy (correct / errors / unsure), completeness (yes / no / unsure), intelligibility (yes / no / unsure), error severity (0–3), error categories (PRD §9), problem words by position |

- **Intelligibility is rated per segment**, in both modes (one judgment per segment). This is
  the scoring unit for the provisional ≥90% challenge-intelligibility target.
- **Blind perceived intelligibility is not evidence that every word was spoken.** Only the
  text-assisted completeness judgment addresses missing words. The summary says this next to
  the blind results.
- Presentation order (and so model order) is shuffled with a **random seed recorded** in
  `session.json`. Every rating records the seed and the item's presentation position.
- Optional private notes in both modes.

Scales are defined in `configs/listening.yaml`. Any value sent for a TBD criterion is
rejected.

## Scales

> **These are project-specific scales.** Naturalness (1–5) and error severity (0–3) were chosen
> for this project (C5A). They are **not externally validated MOS (Mean Opinion Score)
> measurements**. Do not compare them with published MOS results. Listening comfort (1–5)
> comes from the PRD. The same caution appears in every listening summary.

**Naturalness** (blind listening, required):

| Value | Meaning |
|---|---|
| 1 | Very unnatural; difficult to listen to. |
| 2 | Mostly unnatural; frequent distracting speech patterns. |
| 3 | Acceptable; noticeable synthetic speech. |
| 4 | Natural; minor synthetic artifacts. |
| 5 | Very natural; close to comfortable human narration. |

**Error severity** (text-assisted verification, required):

| Value | Meaning |
|---|---|
| 0 | None. |
| 1 | Minor. |
| 2 | Major. |
| 3 | Critical. |

Consistency rules for error severity:
- Severity 0 is refused when error categories are selected, or when pronunciation is "errors".
- Severity 1–3 needs at least one error category.

**Listening comfort** (blind listening, required): 1 = very uncomfortable … 5 = very
comfortable (PRD §17).

Each radio button's spoken name includes its meaning (for example "1 — Very unnatural; difficult
to listen to."), so screen-reader users hear the full label.

## Integrity rules

- **Mock audio never enters a session.** A mock run cannot be opened (`listen serve` stops with
  an error). Mock items in a mixed run are excluded, and the page shows only their count.
- Only real audio is served, rated or exported.
- **Ratings are never overwritten.** Each mode is a separate session. A text-mode re-rating is a
  new revision line; the original stays in the session file.
- **A reviewer who has opened a text session for a run cannot start or resume a blind session
  for that run**, because they have seen the text. Do blind listening first.
- Human ratings and automatic audio checks are reported in separate sections. Human results
  are also split by mode.

## Audio status

Each segment's audio is re-checked when the page starts:

| Status | Meaning | Can be rated |
|---|---|---|
| real | model audio, readable, not silent | yes |
| mock | written by the mock model; silent test output, not speech | never enters a session (excluded, counted) |
| missing | no file | no |
| invalid | unreadable or empty WAV | no |
| silent | digital silence | no |
| error | synthesis failed | no |

Only real audio is served to the page.

## Start a session (on the Mac)

Working directory: the repository.

```bash
source "$HOME/.tamil-tts.env"
.venv/bin/tamil-tts listen serve EXP-001 --run <run-id> --reviewer REV-01 --mode blind
```

- `<run-id>` is a folder under `$TAMIL_TTS_OUTPUT_ROOT/EXP-001/`, or `latest`.
- Text mode needs the private manifest: it reads `$TAM_MANIFEST` (or `--manifest`). Text is shown
  only if it matches the run's segment checksum. In blind mode the manifest is optional and is
  used only to reveal the text after each rating.
- The command prints `Open: http://127.0.0.1:8765/?token=...`. Open that address in a
  browser. The token protects the session from other local pages.
- Stop with `Ctrl+C`. To resume, start again with `--session <session-id>` (printed at start).

## Keyboard

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | move between controls (first stop: "Skip to the current item") |
| arrow keys | move within a choice group |
| `Space` | select a choice, or press a button |
| `P` | play or pause |
| `R` | replay from the start |
| `N` / `B` | next / previous item |
| `S` | save the rating |

Shortcuts are ignored while typing in the notes field. Every control has a visible label. The
status line (`role="status"`) announces item changes and saves. Errors are announced in an alert
region. Tamil text is marked `lang="ta"`, so screen readers can switch voice.

## Saving, resuming and exporting

- Each **Save** appends one line to `<run>/listening/sessions/<session>/ratings.jsonl`. Nothing is
  rewritten; the latest line per item wins.
- Session files are **private**. They contain pseudonymous reviewer codes and notes, and stay
  outside Git.
- Export:
  ```bash
  .venv/bin/tamil-tts listen export EXP-001 --run <run-id>
  ```
  This writes a **new** folder `<run>/listening/exports/<export-id>/` containing:
  - `listener_results.jsonl`: one record per session and item, with pseudonymous reviewer code,
    ratings, categories and word positions. No notes, text or paths.
  - `listening_summary.json` and `LISTENING_REPORT.md`: aggregate counts. Automatic checks and
    human judgments are kept in separate sections.

  Export excludes ratings of non-real audio, and ratings whose audio changed after rating
  (checksum mismatch). Every export starts as `review.status: unreviewed`.

## What may enter Git

| Item | In Git? |
|---|---|
| Individual listener records (`listener_results.jsonl`, `ratings.jsonl`, session folders) | **Never** |
| Reviewer notes | **Never** (they are not even exported) |
| Private Tamil text, TAM transcripts | **Never** |
| Raw or generated audio | **Never** |
| Unreviewed exports (`<run>/listening/exports/`) | **Never** |
| Reviewed, anonymized aggregate: `listening_summary.json` + `LISTENING_REPORT.md` | **Yes**, only through `listen publish` |

`.gitignore` blocks the "never" files, and a test fails if any of them is tracked.

To publish an aggregate after you have read it:

```bash
.venv/bin/tamil-tts listen publish EXP-001 --run <run-id> --export <export-id> --reviewed-by REV-01
.venv/bin/tamil-tts listen check-public experiments/EXP-001/listening/<export-id>
```

`publish` copies only the two aggregate files into `experiments/EXP-001/listening/<export-id>/`.
It marks them reviewed (pseudonymous reviewer code and date) and refuses to overwrite. It also
refuses the result if `check-public` finds a problem. `check-public` requires:
- only the two aggregate files, nothing else;
- `review.status: reviewed`, with a `REV-NN` reviewer code and a date;
- no per-record or private fields (notes, reviewer ids, session ids, word positions);
- no Tamil text and no absolute paths.

Anonymity caution: with very few reviewers, an aggregate can still reveal an individual's
ratings. **OPEN QUESTION:** the minimum number of reviewers before publishing.

## Open questions

- **RESOLVED (C5A):** `listener_results.jsonl` is never committed. Only reviewed aggregates are.
- **RESOLVED (C5A):** Naturalness 1–5 and error severity 0–3 (project-specific, not MOS).
- **RESOLVED (C5A):** Intelligibility is rated per segment.
- **OPEN QUESTION:** Minimum number of reviewers before an aggregate is published.
- Not yet implemented: A/B comparison, and 5–10 minute sustained-listening sessions (PRD §17).
