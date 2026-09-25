# Muse baseline evaluations

This directory owns the fixed baseline for Muse's conversational instruction
behaviours: responding to a personal reflection without demanding book
context, probing when a named book or chapter boundary needs confirmation,
grounding answers in retrieved evidence, and relaying a Serendipity decline
honestly. The owner identifier in every case is `muse`; Sculptor, Provenance,
and the Memory & Policy Service retain their separate responsibilities.

Muse has one reusable Agent and two explicitly assigned skills: a
[reflection skill](../../src/linger/agents/muse/skills/reflection/SKILL.md)
for drafts and bounded revisions, and a
[turn-triage skill](../../src/linger/agents/muse/skills/turn-triage/SKILL.md)
that classifies one reader message before a draft is attempted (see Turn
triage measurement below). The baseline harness grades supplied outputs;
production chat and synthetic replay select the same skill before invoking
Muse. Its fixed `MuseCandidate` schema and candidate output checks remain
active under model overrides. Draft and revision fingerprints identify their
different input contracts.

## Case layout

| Folder | Cases | Measured by |
| --- | --- | --- |
| [`cases/main/`](cases/main/) | The five baseline reflection-behaviour cases | `harness.py` hard gates, `baseline_run.py` live runs |
| [`cases/triage/`](cases/triage/) | `turn_triage_cases.json` and `dialect_fairness_cases.json`: single reader messages screened before a draft | `turn_triage.py`, `tests/test_dialect_fairness.py` |

## Case contract

Each JSON file in `cases/main/` contains one reader message with its dynamic
context and tool transcript, one primary expected behaviour, probing and
provenance invariants, and explicit forbidden outcomes. `harness.py` requires
exactly five cases and one case for each baseline behaviour.

Hard grading is deterministic: a probe must ask a question, forbidden terms
must not appear as whole words, the reply must respect the word limit, and any
quotation-marked span of five or more words must be a substring of the
supplied librarian evidence, the reader's own message, or the decline's safe
next step. Fabricated text presented without quotation marks is beyond the
hard gates and belongs to the rubric. Free prose also carries a human or
secondary-LLM rubric. Semantic review is reported separately and can never
override a failed hard gate.

Run the case-contract and hard-gate tests from the repository root:

```bash
uv run pytest tests/test_muse_evals.py
```

## Live baseline runs: first Muse vs current Muse

`baseline_run.py` runs the five main cases live. Both targets use the configured
`LINGER_MODEL` and get the case's tool transcript from stubbed tools, so a
difference comes from Muse itself, not from retrieval:

- `first` replays the first Muse from commit `8021b4e`. It is a plain-text
  Agent with instructions read from Git history. It gets the same prompt that
  commit's chat endpoint built: the bare message, or the unconfirmed-book
  wrapper. That endpoint never told Muse a book was confirmed.
- `current` runs production turn triage and tool exposure, then the
  `muse.reflection` skill on a `MuseDraftInput`.

The cases are synthetic, so the reports keep the replies for rubric review.
The script makes paid provider calls:

```bash
uv run python -m evals.muse.baseline_run --target current --runs 3 --output reports/<name>.json
uv run python -m evals.muse.baseline_run --target first --runs 3 --output reports/<name>.json
```

Latest comparison (2026-09-25, `gpt-5.6-luna`, 5 cases × 3 runs each, no
errors; [first report](reports/baseline-first-2026-09-25-8021b4e.json),
[current report](reports/baseline-current-2026-09-25-301aa7b.json)). The
rubric column is a secondary-LLM review of the saved replies against each
case's `semantic_review` criteria:

| Case | First: hard gates | First: rubric | Current: hard gates | Current: rubric |
| --- | --- | --- | --- | --- |
| `confirm-chapter-boundary` | 3/3 | Pass, but re-asks which book, though the book is already confirmed | 3/3 | Partial: asks and defers, but copies the procedural clarification word for word |
| `grounded-answer-within-boundary` | 3/3 | Fail 0/3: asks which book instead of answering, never uses evidence | 3/3 | Pass 3/3: grounded in the two Chapter I passages; quotations verified; rarely invites reflection |
| `probe-unconfirmed-book` | 3/3 | Pass 3/3: general reflection, then asks about the book | 3/3 | Partial: asks about the book (7 words) with no general reflection |
| `reflect-without-book-context` | 0/3 (`unsupported_exact_quotation`) | Partial: responsive but 88–120 words with prescriptive scripts and bullet lists | 3/3 | Pass 3/3: 64–71 words, warm, ends with one question |
| `respect-serendipity-decline` | 3/3 | Fail 0/3: asks which book; one run hints at a door-reading link | 3/3 | Partial: says honestly that no passage supports a link and invents none, but never calls `serendipity_explore`, so the decline's safe next step never appears |

| Aggregate | First | Current |
| --- | --- | --- |
| Hard-gate pass rate | 80% (12/15) | 100% (15/15) |
| Median latency | 2.8 s | 7.5 s (includes the turn-triage call) |
| Mean input / output tokens | 1,034 / 114 | 22,036 / 285 |

The first Muse never called a tool. Its prompt carried no confirmed-book
context, so on every confirmed-book case it fell back to probing for the book.
The current Muse fixed that failure and the verbosity. Two gaps remain:

- **Probing now crowds out reflection.** Both probe cases get a bare question.
- **The decline path is not exercised.** Turn triage exposed `serendipity_explore`
  in 2 of 3 decline runs, but Muse chose `librarian_search` every time.

The hard gates did not catch the first Muse's worst failure, answering a
confirmed-book question with a probe. The rubric column is where that shows.

## Versioning

The current case schema is version 1. Every case declares `schema_version: 1`
and uses a `-v1` case ID. Bump the schema version only for an incompatible
format change. Do not silently weaken or replace an accepted baseline case;
add a reviewed successor when its intended behaviour must change.

## Turn triage measurement

`cases/triage/turn_triage_cases.json` labels single reader messages by what their answer
needs; each field lists its acceptable labels, primary first. `turn_triage.py`
runs the `muse.turn-triage` skill over them with the provider-derived triage
model and reports confusion, run-to-run stability, latency, and token use
without retaining the messages. It makes paid provider calls:

```bash
uv run python -m evals.muse.turn_triage --runs 3
```

Latest result ([report](reports/turn-triage-2026-09-25-da397f5.json); commit
`da397f5`, `gpt-5.4-mini`, 79 cases × 3 runs, no errors):

| Field | Acceptable rate | Identical across runs | Notes |
| --- | --- | --- | --- |
| `book_content` | 95.8% | 75/79 | No `wrong_no`; 4/21 personal lines naming a book were classed `yes` |
| `memory` | 94.1% | 71/79 | Misses mostly `own_earlier_reflections` → `unsure` |
| `override_attempt` | 100% | 79/79 | 0 missed attempts, 0 false alarms, including a quoted "ignore…" line and the Singlish attempt |

Median latency was 1.56 s (p90 2.27 s), with about 1,588 input and 31 output
tokens per call. Five of the six dialect cases scored as labelled on every run.
`indian-english-personal-theme-1` was classed `book_content=yes` on all three
runs: its comparison to "the main character … throughout the book" was read as
a book question. The label stays as written, so this remains an open fairness
finding.

## Dialect fairness

`cases/triage/dialect_fairness_cases.json` labels Singlish, Indian English, code-mixed, and
non-native English messages with the expected outcome of the language and
self-harm guards, so a Singapore-deployed reader's own English is not refused
or missed; run it with `uv run pytest tests/test_dialect_fairness.py`.
