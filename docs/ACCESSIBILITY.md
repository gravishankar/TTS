# Accessibility

Derived from [PRD.md](PRD.md). Section references (§) point to the PRD.

## 1. Who the product serves (§5)

- **Primary users:** visually impaired Tamil listeners and elderly Tamil listeners consuming
  books/guides for sustained periods.
- **Secondary users:** volunteers/reviewers producing and validating accessible audio.

The goal is accessible listening, not generic "human-like" speech. Naturalness must never be traded
for intelligibility, completeness or listening comfort (§4).

## 2. Accessibility requirements

| Requirement | Source |
|---|---|
| Every word of the source text is spoken: zero missing or silent segments (hard gate) | §10, §16 |
| Source Tamil text is never altered; normalization is kept separate and auditable | §10, §20 |
| Numbers, dates, currency, percentages and units are read through explicit rules | §9 NORM-NUM, §10 |
| Hard Tamil phonology is pronounced correctly (ல/ள/ழ, ர/ற, nasals, vowel length, gemination, Grantha) | §9 |
| Prosody follows clauses, punctuation, dialogue and long literary sentences | §9 PROSODY |
| Mixed Tamil-English text, names and abbreviations are handled | §9 MIXED |
| Literary and older Tamil vocabulary is read correctly | §9 LITERARY |
| Pace, pauses and clarity support long listening without fatigue | §9 ACCESS |
| Works offline on the listener's side: at least one offline-capable candidate | §5, §24 |

## 3. Measuring accessibility (§16, §17)

| Metric | Initial target | Role |
|---|---|---|
| Completeness | 100%; 0 missing/silent segments | Hard gate |
| Frozen regression | No material regression | Hard gate |
| Pronunciation errors | ≥30% reduction vs selected baseline | Quality target; recalibrate after EXP-001 |
| Challenge intelligibility | ≥90% | Human authoritative |
| Comfort | Median ≥4/5 and not below baseline | Accessibility |

- Metrics are never collapsed into a composite score. Better naturalness cannot compensate for
  omitted text.
- Human Tamil judgments outrank ASR for pronunciation.

## 4. Human listening protocol (§17)

- Launched locally with `tamil-tts listen EXP-xxx`. Audio paths stay on the local machine.
- Blind, randomized A/B comparisons where possible.
- Captured per item: clearer (A/B/same), pronunciation error category, problem word, optional notes,
  comfort 1–5.
- Intelligibility is tested **without** showing text. Pronunciation is tested separately **with**
  text visible.
- Sustained listening sessions of 5–10 minutes test comfort and fatigue. ~15-minute chapter
  validation is added later.
- Results are written to `listener_results.jsonl`. Claude analyses the structured results and never
  ingests audio.

## 5. Evaluation data for accessibility (§8)

- The CHALLENGE split targets hard phonology and real difficult book prose. At least half of its
  duration is natural literary/book prose.
- TEST and CHALLENGE are frozen after EXP-001 and never used for training.

## Open questions

Things the PRD does not specify. These must not be assumed.

1. **OPEN QUESTION:** Whether the listening interface itself must be usable by visually impaired
   reviewers (screen reader support, keyboard-only operation, large text, high contrast), and
   which standard applies (e.g. WCAG level).
2. **OPEN QUESTION:** Who the listeners are, how many there are, and whether listener groups must
   include elderly and visually impaired people rather than only volunteers.
3. **OPEN QUESTION:** How challenge intelligibility (≥90%) is scored: by word, by segment or by
   utterance, and how the listener's response is captured when no text is shown.
4. **OPEN QUESTION:** Target speaking rate and pause lengths for the ACCESS tag, and whether
   listeners can adjust speed.
5. **OPEN QUESTION:** Wording and anchors of the 1–5 comfort scale.
6. **OPEN QUESTION:** Delivery format for end listeners (plain audio files, chaptered audiobook,
   DAISY or other accessible formats) and navigation needs.
7. **OPEN QUESTION:** Preferred voice characteristics (gender, age, register/dialect) for primary
   users.
8. **OPEN QUESTION:** The rules for reading mixed Tamil-English text (read English as English,
   transliterate, or something else).
9. **OPEN QUESTION:** Consent and privacy terms for TAM speakers and listener-study participants.
