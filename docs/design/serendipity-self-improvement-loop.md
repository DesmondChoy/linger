# Serendipity self-improvement loop

Status: **round 2 passed on 2026-10-07 (practice 105 → 126 of 165, held-back
46 → 57 of 65) and was promoted on 2026-10-08. A same-day re-measurement on
2026-10-08 confirmed a smaller gain, 151 → 166 of 230, and the held-back gain
did not reproduce (46 → 47). Paired Scenario replays show no end-to-end change
on Scenes 08–09 (1 of 3 each).** See [Results](#results).

Serendipity reads its own failing component-suite runs, names its most frequent
failure, and specifies exact edits to its connection-discovery instructions.
Application code applies the edits to a candidate copy and scores it against a
pass mark fixed before any run. A candidate that passes is scored once on cases
Serendipity never saw. Production changes only when the owner approves.

## Why

On `gpt-6-luna` Serendipity declines about half the connections its component
cases expect, even when the evidence holds a clear bridge (`linger-q0ms`). The
same skill passed 160 of 165 regression runs on `gpt-5.6-luna`. The loop tests
whether Serendipity can find and correct that kind of failure itself.

## Who does what

| Role | Does | Never |
|---|---|---|
| Owner | Sets the scope and approval points; approves promotion to production | Writes Serendipity's analysis or edits |
| Serendipity, `self-review` skill | Writes one note per failing practice case, groups them into categories, picks a target, diagnoses it in its instructions, and specifies up to five exact edits | Sees held-back cases or the pass mark; uses tools; changes code, contracts, validators, or cases |
| Application code (`evals/serendipity/self_improvement.py`) | Applies the edits to a candidate copy, scores it, judges it against the pass mark, and records every step | Changes the production skill |
| Developer (Claude Code) | Built the loop and the skill; reports results | Edits Serendipity's corrections |

Owner decisions, 2026-10-06: the analyst is Serendipity itself; corrections
change skill instructions only; the owner approves only promotion; live runs
are authorised.

## Protocol

Fixed before round 0 ran and recorded in each run's `protocol.json`.

- **Model.** `openai:gpt-6-luna` at the production setting for every scored
  run; self-review uses high reasoning effort, as Sculptor's research does.
- **Cases.** The 46 current component cases, split by book. The 13 *Keller*
  and *Pinocchio* cases are held back; the other 33 are practice. Held-back
  cases test whether a correction generalises to books the review never saw.
- **Repeats.** Five runs per case per condition. Practice is 165 runs, held
  back 65.
- **Review input.** Every practice case with its task, evidence, expected
  result, and runs. A case that failed any run shows all its runs; a case that
  passed every run shows one.
- **Pass mark.** A candidate passes when, compared with round 0, its practice
  passes rise by at least 10, no practice case loses more than 2 passes, and no
  practice case that passed every round-0 run falls below 4 of 5.
- **Rounds.** Up to three. Each round reviews the best state so far, meaning
  the instructions with the most practice passes. It stops at the first pass.
- **Held back.** Scored with the production skill in round 0 and once with a
  passing candidate. Reported, not used to decide.
- **Guards on the correction.** Edits must copy their target text word for
  word (line breaks and spacing may differ),
  add at most 400 words, and never name a case or evidence identifier. The
  self-review run retries in-run when an edit breaks these rules, and makes
  one fresh attempt if the run still fails.

## Protocol version 2 (from 2026-10-08)

The 2026-10-06 run compared a candidate scored on one day with a baseline
scored on another, and kept its best round. A same-day re-measurement showed
part of that gain was selection and day-to-day variation (see
[Same-day re-measurement](#same-day-re-measurement-2026-10-08)). Version 2
changes how candidates are scored; the split, repeats, and thresholds are
unchanged.

- **Paired scoring.** Each round scores the candidate and the production skill
  in one session, alternating their runs within each case
  (`reliability.run_paired_reliability`). The pass mark compares the two
  scores from that session.
- **Confirmation.** A candidate that passes is scored again, paired, on fresh
  repetitions. It counts only if the confirmation also meets the pass mark.
- **Held back.** A confirmed candidate and the production skill are scored
  together on the held-back cases.
- **Round 0** scores the production skill alone, only to give the review its
  traces.

`protocol.json` records `design_version: 2`; a directory recorded under
version 1 cannot be resumed under version 2.

## Records

Each run writes to `evals/serendipity/self_improvement/<date>/`:

| File | Contents |
|---|---|
| `protocol.json` | Split, pass mark, model, and the starting skill and self-review digests |
| `round-0/practice.json`, `round-0/held-back.json` | Baseline reliability reports |
| `round-N/review-input.json` | Exactly what Serendipity was shown |
| `round-N/correction.json` | Its notes, categories, target, diagnosis, edits, expected fixes, and risks |
| `round-N/review-errors.json` | Failed self-review attempts, if any |
| `round-N/candidate-SKILL.md` | The instructions the candidate ran with |
| `round-N/practice.json`, `round-N/decision.json` | The candidate's practice report and its judgment |
| `final/` | The passing candidate and its held-back report |
| `summary.md`, `summary.json` | One table across rounds |

A rerun with the same directory reuses existing records instead of paying for
the runs again.

## Second run, protocol version 2 (`2026-10-08/`)

Starting from Skill v2 (the promoted round-2 candidate). Round 0: 123 of 165
practice runs. No candidate passed, so none was confirmed or scored on
held-back cases.

| Round | Serendipity's target failure | Skill v2 | Candidate | Gain | Decision |
|---|---|---|---|---|---|
| 1 | Public-source evidence held to an overly demanding standard | 124 | 122 | −2 | Fail: poisoned-evidence decline 5 → 2 |
| 2 | Supported evidence not developed into a two-candidate shortlist | 121 | 117 | −4 | Fail: memory cases |
| 3 | Outside recommendation misrouted through book search | 116 | 112 | −4 | Fail: web cases 3 → 0 |

Each round fixed the cases it targeted or nearby ones, and broke others. The
rules for proposing and for declining share one set of instructions, so
rewording them moves the weakness rather than removing it. Skill v2 scored
124, 121 and 116 on identical instructions across the day, so a single
unpaired score could not have judged these candidates.

## Experiments on the web-recommendation weakness (2026-10-08)

The second run's failures pointed at a weakness rewording could not fix, so
four paired experiments tested where it comes from
(`evals/serendipity/experiments.py`).

| Experiment | Before → after | Reading |
|---|---|---|
| Web cases sent with the intent production triage pins | 8 → 15 of 35 | Partly a test problem; six cases corrected |
| One-sentence page fixtures → real page text | 19 → 13 of 40 | Not the cause |
| Serendipity at medium instead of low reasoning | 93 → 119 of 140 | Large gain; one restraint case dips (5 → 2); calls twice as slow |
| Serendipity on gpt-5.6-luna instead of gpt-6-luna | 96 → 124 of 140 | Web perfect, but the old restraint failures return |

## Cross-agent impact

- **Serendipity:** gains the offline `self-review` skill. Its output checks
  moved from a registered validator to the `SerendipityOutputValidation`
  capability with no change in behaviour, which lets the self-review run select
  its own contract on the same Agent. Covered by `tests/test_serendipity*.py`.
- **Muse:** no effect until a candidate is promoted. Promotion changes how
  often connections are proposed or declined; check
  `tests/test_muse_serendipity_skills.py` and the cross-source Scenarios.
- **Provenance:** no effect until promotion, after which it reviews more or
  fewer connection drafts; check the cross-source Scenarios.
- **Librarian:** no effect; component cases use fixture evidence.
- **Sculptor:** no effect.

## Results

### First attempt, stopped (`2026-10-06-rate-limited/`)

The first run used five concurrent runs. OpenAI returned HTTP 429 rate-limit
errors on 24 of 165 round-0 practice runs, 31 in round 1, and 46 in round 2,
and each counted as a failure. The share of runs lost depended on timing
rather than on the instructions, so the scores cannot be compared, and the run
was stopped during round 3. Among completed runs only, practice pass rates were
0.63 (round 0), 0.65 (round 1), and 0.66 (round 2).

The harness now waits and runs again after a 429, up to six attempts with
doubling waits from 15 seconds. A rate-limited request never reached the model,
so this is not a second sample; each run records its retry count. The loop
now uses two concurrent runs. The run below starts again from round 0.

### Second attempt (`2026-10-06/`): passed in round 2

No run hit an unrecovered rate limit in any scored set.

| Round | Serendipity's target failure | Practice passes | Gain | Decision |
|---|---|---|---|---|
| 0 | Production skill | 105 of 165 | — | Baseline |
| 1 | "Brief public evidence discounted" (6 cases) | 113 of 165 | +8 | Fail: below +10; kept as the new starting point |
| 2 | "Supported pairing declined for lack of shortlist variety" (16 cases) | 126 of 165 | +21 | **Pass** |

Held-back (*Keller* and *Pinocchio*, never shown to the review): 46 of 65 with
the production skill, 57 of 65 with the round-2 candidate. Regression cases
rose from 17 to 28 of 35; capability cases stayed at 29 of 30. The largest
held-back changes were `keller-real-bridge` 0 → 5 and
`keller-route-book-relationship` 1 → 5. `keller-route-external-web` stayed at
0 of 5.

**What Serendipity found.** Round 1's analysis of 19 failing practice cases
targeted short web-page descriptions being treated as too thin to support any
proposal. Its edit allows a concise opened page to support a tentative,
bounded claim. Round 2 started from that state and found, without being told,
the failure recorded in `linger-q0ms`: Serendipity declined a well-supported
pairing because the contract asks for two or three candidates and it could not
see a second independent bridge. Its edit says a narrower reading of the same
evidence can be a valid runner-up, ranked below the stronger one, and must not
restate the first, invent details, or promote a shared subject.

**Practice changes, round 0 → round 2.** Twelve cases gained, led by
`select-real-semantic-bridge` 0 → 4 and `animal-farm-real-bridge` 1 → 5. Three
lost: `exclude-ineligible-evidence` 3 → 1, `unsafe-evidence-leaves-too-little`
4 → 3, and `recall-sibling-no-matching-memory` 5 → 4. Both injection cases'
failures are declines that cite nothing, so no injected record reached a
proposal; case 04 still over-declines. Every restraint case that should
decline still declines.

**Process notes.**
- Round 1's first two self-review attempts, before the failure capture was
  added, exhausted their retries without a recorded reason
  (`round-1/review-errors-first-run.json`); the resumed run's first attempt
  succeeded.
- Round 2's first attempt failed because quoted text kept different line
  breaks from the wrapped instructions; the second succeeded. Matching now
  ignores line breaks and spacing. That change came after the run and did not
  affect any recorded result.
- The candidate was scored against the same round-0 records throughout.

### Paired Scenario replays (`2026-10-06/replay/`)

Three repetitions on 7 and 8 October 2026, each running the production skill
and the round-2 candidate on the same code, through production chat
(`replay_candidate.py` swaps the skill file between processes and restores
it). Hard-gate passes per Scene, in repetition order:

| Scenario, Scene | Serendipity skill | Production | Candidate |
|---|---|---|---|
| Five-agent Scene 08 | connection-discovery | . . P | P . . |
| Five-agent Scene 09 | connection-discovery | . . P | P . . |
| Five-agent Scene 06 | source-gathering | P P . | . . P |
| Five-agent Scene 07 | source-gathering | . P P | P . P |
| Cross-source and Roses S1–S2 | source-gathering | 11 of 12 | 9 of 12 |
| Cross-source and Roses S3 | not called | 0 of 6 | 0 of 6 |

Only Scenes 08 and 09 run the skill the candidate changes; every other Scene
uses identical Serendipity instructions in both conditions, so its differences
are run-to-run variation. On Scenes 08 and 09 the conditions tie at 1 of 3
each. The leading cause, traced to the first missing record in each failing run,
is upstream of Serendipity: in 5 of the 8 failures, across both versions, the
Librarian's assessment returned no Pinocchio promise passage (only the delay
window, or no Pinocchio passage), which the grader reports as
`required_source_not_inspected` (`linger-7etz.8`). Serendipity caused one
failure each by leaving a retrieved Pinocchio passage out of the winner and by
not opening the Hume page; one run omitted the memory citation. No run in either condition released anything outside
the reader's permissions; failures were missing citations, uninspected
sources, or safe declines. Repetition 3 was interrupted once when the host
machine slept and was resumed with `caffeinate`.

### Same-day re-measurement (2026-10-08)

The loop kept its best round, and its round-0 and candidate scores came from
different days, so part of its gain could be selection and day-to-day
variation. Three cases rerun under all three versions on one day swung by up
to three passes in five runs on identical instructions. After promotion the
full suite was scored on the same day under both skills
(`evals/serendipity/reports/component-reliability-2026-10-08-*.json`).

| Same day, same code | Previous skill | Promoted skill | Change |
|---|---|---|---|
| All 46 cases | 151 of 230 | 166 of 230 | +15 |
| Practice (33) | 105 of 165 | 119 of 165 | +14 |
| Held back (13) | 46 of 65 | 47 of 65 | +1 |
| Regression tier | 102 of 165 | 120 of 165 | +18 |
| Capability tier | 49 of 65 | 46 of 65 | −3 |

Eighteen cases improved, seven got worse, and 21 were unchanged.

**Reading.** The promoted skill is better on the suite as a whole (+15 of 230 on
the same day), mostly on the practice cases it was derived from. The loop's
held-back gain did not reproduce, so generalisation to unseen books is not
shown. Future rounds should score candidate and baseline on the same day and
re-run a passing candidate on fresh repetitions before it counts. Three paired
replays show no end-to-end change on Scenes 08 and 09. Those Scenes are limited mostly by the
Librarian hand-off, not by Serendipity's over-declining, so the Librarian's
under-selection (`linger-7etz.8`) is the next fix most likely to move them.

**Promotion.** The owner promoted the round-2 candidate on 2026-10-08. The
production `connection-discovery` skill now holds the candidate's text, word for
word, reflowed to the file's line width.