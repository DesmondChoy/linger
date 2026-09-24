# Librarian evaluation rerun — book-only results

Eight of the eleven listed live evaluations completed on September 17, 2026 with `openai:gpt-5.6-luna`: six scenarios covering 23 Scenes, plus two 12-case component suites. That is 47 completed Scenes/cases. The two cross-source scenarios and the external-source smoke test remain paused pending explicit Exa query/URL permission. Four additional historical scenarios failed preflight and were not run.

The main result is mixed: focused retrieval now supplies the specific stopping events for Alice, Douglass, and Keller, and all five book scenarios infer their specific stopping points at the correct chapter. However, ambiguous progress still causes unsafe grants and disclosures in Douglass, Keller, and Pinocchio. Passing retrieval targets does not resolve those permission errors.

## Scenario results

Recorded results are **13/23 Scenes** and **14/24 judgments passed**. The five recent books total **12/20**, compared with the earlier **14/20**. These are single runs, not a controlled reliability estimate. Strict support matching, a model-output failure, and an ungraded answer-completeness gap make the aggregate score insufficient on its own.

| Scenario | Earlier run | New recorded result | Interpretation | Evidence |
| --- | ---: | ---: | --- | --- |
| Alice event-led | 3/4 | 3/4 | Correct Chapter 3; extra valid support rejected. Ambiguity safely clarified. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-17T214357+0800-2ba128d6.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af98460f600a2cc7231c8c6b2114-d4136ce4cfb5e010) |
| Animal Farm | 3/4 | 2/4 | Correct Chapter 5; extra valid support rejected. Ambiguity hit a model-output error and safely clarified. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-17T215430+0800-d84ab25f.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0afa2a0942b3907e9f1cfb7ec0fea-74b613ca6cca78e5) |
| Pinocchio | 2/4 | 2/4 | Correct Chapter 9; support coverage differs. Ambiguity wrongly granted Chapter 26 and disclosed plot. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-17T215743+0800-de5c5031.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0afa5cb935973b8425aa70984a834-95b993be1f081ff2) |
| Douglass | 3/4 | 2/4 | Correct Chapter 7; extra valid support rejected. Ambiguity wrongly granted Chapter 8 and disclosed plot. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-17T214801+0800-7727ec76.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af9c27c77d07b801f827e72397cd-b390b272c2ded888) |
| Helen Keller | 3/4 | 3/4 | Correct Chapter 10. Inference pass hides missing quotation; ambiguity wrongly granted Chapter 10 and disclosed plot. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-17T215102+0800-51bcecb8.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af9fddf4c083745004bd6af95bd6-0ba58d6185926640) |
| Alice Pigeon | — | 1/3 | Correct Chapter 5 became a Chapter 4 search. Ambiguity wrongly granted Chapter 5, but final response safely declined. | [Review](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-17T214304+0800-65903aa4.md>), [Logfire](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af988e1c3c95d05c5901d000c3fa-a235f105789727b9) |

Every Scene, including passing and failed ones, has a completed review in the linked reports. Raw grades are preserved.

## What changed in the observed behavior

**Specific stopping events now reach the boundary judge.** Alice reaches Chapter 3, Douglass Chapter 7, and Keller Part I Chapter 10. The earlier runs clarified instead. The new Alice and Douglass failures concern additional valid support, not a wrong chapter. Farm has the same extra-support issue. Pinocchio reaches the correct Chapter 9, but its proof omits the full adopted embrace occurrence and includes a different reader-mentioned support passage. These are potential grading false negatives requiring explicit evaluator/expectation review, not silent relabeling.

**Ambiguity remains unsafe.** Douglass receives Chapter 8 at 0.97 confidence even though both Chapter 8 and Chapter 10 return episodes were in the private candidates. It releases valuation, estate deaths, and grandmother consequences. Pinocchio receives Chapter 26 at 0.98 despite both Chapter 9 and Chapter 26 alternatives; it releases the Shark/companions episode and a Chapter 25 promise. Keller receives Chapter 10 at 0.99 and identifies the crab episode, although the reader omitted animal and setting; the competing canary episode was missing from its private pool. Provenance accepted these granted scopes. Follow-ups: `linger-14sc`, `linger-rt2x`, and `linger-69gn`.

**Muse can reduce a correct inferred ceiling by one.** In Pigeon, inclusive Chapter 5 becomes a search for Chapter 5 marked `started`, so only Chapters 1–4 are searched. Keller similarly turns inferred 10 into a search through 9 and refuses the available quotation. Keller still passes its spoiler-only grade because that Scene does not grade the quotation request. This is a concrete misleading pass; follow-up `linger-hn7j` covers the application handoff, and `linger-42d3` covers grading gaps.

**Farm failed safely on invalid model output.** Its ambiguous discussion produced invalid structured uncertainty twice. The application returned clarification without granting a scope, searching response evidence, or releasing plot. The recorded handoff failure comes from the absent valid model output, not an observed content leak. Follow-up: `linger-bdtp`.

**Personal-only controls stayed personal.** All six returned useful personal reflection without book retrieval. Alice and Pinocchio grounded passes still leave some richer contextual details from adopted prose ungraded; their per-Scene reviews explain that limit.

## Standalone results

| Evaluation | Coverage | Evidence recall | Precision | Strength accuracy | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Local retrieval benchmark | 180 searches: 12 cases × 5 strategies × 3 repetitions | 91.67% | 82.64% candidates | 91.67% retrieval support | Selected hybrid reranking; precision target missed; scope/citation gates passed |
| Direct Librarian assessment | 12/12 cases | 95.83% | 100% selected evidence | 91.67% | One expected-label mismatch; one strict blank-line citation comparison failed |
| Librarian → Muse → Provenance release | 12/12 cases | 91.67% | 100% final citations | 91.67% | Aggregate targets passed; answerable release rate 100%; no measured spoiler exposure |

The fixed `identity-theme` expectation is `weak`, while both live paths judge a directly supporting Chapter 5 passage `sufficient`. The query does not explicitly require the second gold episode; this may be a stale coverage/strength expectation. The original grades remain unchanged. The direct `drink-me` citation resolves to canonical text but differs from the raw source by one normalized blank line, so its strict comparison fails. Neither observation establishes fabricated evidence.

The release suite loses one of two gold ranges on `pigeon-serpent` after Provenance requests a revision. Its metadata-only report does not retain the final reply, so semantic completeness is unverified. These limits, all 12 case rows, logs, and exact reports are in the [standalone analysis](standalone/analysis.md).

## Evaluation preparation and verification

The initial release attempt stopped locally before any provider call because its introduction was parsed as part of the book title. The runner now puts the completed chapter before the title and binds the current reader message. The notebook also binds that message and omits the removed `query` tool argument. The original questions, chapter ceilings, frozen expectations, notebook outputs, and all adopted scenario bytes are preserved. The production parser bug remains `linger-fasa`; the notebook compatibility task `linger-4tf7` is closed.

Verification: 247 focused tests and 196 subtests passed before live work; the runner changes passed an additional focused check of 28 tests and 139 subtests. These are separate overlapping test selections, not additive unique totals. All twelve scenario source/adoption hash sets still match preflight. Only the evaluation runner, notebook, one new compatibility test, generated reports, and Beads records changed during this rerun; no production runtime fix, commit, or push was made.

All six scenario processes completed, with one Farm boundary-model execution failure handled safely inside the run. Each approved suite ran once; no failed live case was rerun and no optional semantic-review model call was added. All six scenario reports emitted Logfire evaluation links and successful flushes; both component suites also flushed. Remote visibility has not been independently read back. Standalone usage totals are unavailable because the old harness calls an SDK usage property as a method; they are not zero (`linger-c0kp`).

## Unrun coverage

| Evaluation | Coverage | Reason |
| --- | ---: | --- |
| `alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12` | 3 Scenes | Automatic approval review requires explicit permission for Exa query/URL payloads |
| `cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12` | 3 Scenes | Same Exa permission pending |
| `cross-source-outside-essay-v1` | 1 case | Same Exa permission pending |
| Historical Caterpillar, kitchen, quotation scenarios | 7 Scenes | Current-schema validation failures |
| Historical Alice identity connections | 3 Scenes | Missing independent Ground truth adoption |

The blocked historical Scenes each have a completed preflight review linked from [preflight.json](preflight.json). No adoption or schema was fabricated. Fixture-only evaluations of other agents are excluded because they do not execute the Librarian role.

[Full results and run manifest](results.json) · [Source snapshot](runtime-snapshot.json) · [Earlier five-book report](../five-book-replay-2026-09-17/evaluation-report.md)
