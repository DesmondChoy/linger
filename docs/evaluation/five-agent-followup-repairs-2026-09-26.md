Two repairs are verified, but reviewer accuracy remains unresolved. Librarian
now receives structural validation errors while it can still repair its answer.
Evaluation reports now separate automated grades, semantic review, and execution
failures. Neither increasing Provenance's reasoning effort nor reducing its task
to one claim reliably fixed the recorded wrong speaker attribution.

This follows [the stage experiments and runs 14–15](five-agent-stage-experiments-2026-09-26.md).
Those runs scored 7/9 and 6/9 on automated checks, with semantic defects in some
passing Scenes. No further full Scenario replay was performed during this
follow-up. The new Librarian behavior therefore has focused verification, not a
new nine-scene result. Backstory, Ground truth, and adoption remain unchanged.

The Librarian repair shares validation between the bounded model retry loop and
the final application check. It covers selected records, requested-part support,
exact reader wording, unknown part indices, and sufficient-coverage claims.
Schema-accepted numeric strings receive the same checks as integer indices.
Final application validation remains independent, and retry budgets are unchanged.

Two live repair probes began with a locally injected, saved faulty response.
Each then used one real provider response to repair the defect:

| Saved failure | Repair result | Remaining semantic problem |
| --- | --- | --- |
| Run 13, Scene 8: sufficient coverage omitted a requested part | Returned weak evidence with that part explicitly unsupported; retained selected records | Still described a promise absent from the selected Pinocchio excerpt |
| Run 15, Scene 7: invented reader wording | Replaced it with the exact reader span, "Do they?"; retained requests and selected records | Still described Keller's lake passage while selecting her college passage |

Both outputs passed the final structural guard. This establishes that the repair
path works for the recorded defects. It does not measure how often the model
naturally makes those mistakes, or establish correct interpretation of sources.
Bead `linger-7etz.2` is closed for its validation-feedback scope.

Provenance's existing full review was tested with low and medium reasoning on
identical frozen inputs, three repetitions per case and setting. Each figure
below concerns the target source claim, rather than the whole-response verdict.

| Target claim | Low reasoning | Medium reasoning |
| --- | --- | --- |
| Correct Pinocchio speaker accepted | 2/3 | 3/3 |
| Incorrect Lamp-Wick speaker rejected | 2/3 | 2/3 |
| Grounded Alice interpretation accepted | 3/3 | 3/3 |

Medium reasoning still accepted the wrong speaker once. It also used more output
tokens and time in this sample. There is no basis here for adopting it as a fix.
The complete comparison included a fourth, disputed Keller paraphrase, giving
24 completed reviews and 28 successful provider responses including retries.
Two additional attempts ended with HTTP 429 and are recorded separately.

The earlier classification of Keller's patchwork paraphrase as a definite
negative control was too strong. Her complete paragraph connects reading to the
substance of her mind and describes both patchwork compositions and mixed
thoughts and feelings. The interpretation is debatable; accepting it is not
enough to establish an error. The original case remains in the evidence, but is
excluded from binary accuracy claims. New controls instead distinguish her
actual statement that she cannot always distinguish her own thoughts from those
she read from the contradictory claim that she can always distinguish them.

A second experiment used the same reusable Provenance Agent with an experimental
task containing one claim group, its full canonical passages, and the whole
reply for context. It omitted prior review findings and the unrelated policy
checks. Outputs had to cite literal source excerpts. This is a semantic review
experiment, not a production release decision or full Scenario replay.

| Focused case | Result across three repetitions |
| --- | --- |
| A: simple correct Pinocchio claim | Correctly accepted 3/3 |
| B: simple wrong Lamp-Wick claim | Correctly rejected 3/3 |
| C: grounded Alice interpretation | Correctly accepted 3/3 |
| G: Keller's correct "cannot always" statement | Correctly accepted 3/3 |
| H: contradictory "can always" statement | Correctly rejected 3/3 |
| D: disputed Keller paraphrase | Accepted 3/3; qualitative only |
| E: original recorded Pinocchio claim | Accepted 2/3; one rejection gave an internally inconsistent explanation |
| F: recorded revised answer with wrong Lamp-Wick attribution | Incorrectly accepted 3/3 |

The experiment got all 15 simple binary controls right, then failed the actual
recorded wrong revision in all three repetitions. Its explanations explicitly
assigned Pinocchio's dialogue to Lamp-Wick. The canonical dialogue is identical
in the simple and recorded cases. The reply context and claim wording differ,
so these results do not isolate which difference caused the failure. They do
show that clean controls alone would have falsely qualified this change.
The original correct attribution case also contains speech-versus-thought
wording that should be assessed separately from speaker identity.

The focused experiment completed 24 invocations with 25 successful provider
responses, including one output repair, and no HTTP failures. Together with the
full-review comparison and two Librarian probes, this follow-up completed 50
experiments using 55 successful provider responses. The two saved HTTP 429
attempts are additional. Production Provenance instructions and model settings
remain unchanged; the focused task remains a local experiment.

Reporting now keeps the original hard grade alongside an explicit semantic
status: unreviewed, passed, failed, or inconclusive. Execution diagnostics
separate HTTP/provider failures, model-output errors, proven repair exhaustion,
post-call rejection, and other failures. The available run 15, Scene 9 metadata
supports `model_output_error`; it does not by itself prove an API outage or the
precise terminal retry condition. Run 15, Scene 7's offline reproduction is
labelled separately from the original trace's less specific retrieval failure.

New reports bind their review to immutable extracted facts and verify original
artifact hashes. Legacy reports remain readable with their weaker binding made
explicit. Refreshed reports preserve all original grades and replies. Semantic
review is scoped to the inspected Scenes; Scenes 1–5 remain explicitly unreviewed.
Bead `linger-7etz.4` is closed.

The full offline suite passed 2,542 tests and 6,389 subtests. After a final report
reference correction, all 81 reporting, diagnostic, and CLI checks passed.
Independent review verified 97 evidence references and unchanged source hashes.
Librarian's adjacent checks passed 154 tests and 14 subtests; the experimental
claim task passed 14 offline contract checks. These tests establish code and
contract behavior, not reliable literary interpretation by the model.

Cross-agent effects of the retained follow-up changes are:

- Muse: receives evidence after Librarian's bounded repair; evidence-strength,
  book-request-recall, and existing chat/revision checks cover that handoff.
- Librarian: receives actionable structural feedback; request-plan,
  evidence-strength, and captured-stage tests cover repair and final rejection.
- Serendipity: consumes the repaired book evidence; book-selection and connection
  checks cover that shared boundary.
- Provenance: no production behavior change. Source-attribution controls show
  why both experimental changes remain unadopted.
- Sculptor: no effect. Reporting does not alter any agent's release authority.

`linger-7etz.3`, `linger-7etz.1`, and the parent remain in progress. Reviewer
attribution, source interpretation, requested-content completeness, and the
Scene 8 promise/delay selection remain unresolved. The next reviewer experiment
must pass the recorded full-answer failures as well as minimal controls before
it justifies production adoption. Another full replay would be useful after a
supported semantic repair; repeated full runs alone do not repair these faults.
No commit, push, or remote sync was performed.

Evidence is under `/private/tmp/linger-stage-repair-20260926/`:

- `reviewer_accuracy/full-review-comparison.json` and its frozen inputs,
  transcripts, settings, and failures.
- `focused_claim_results/comparison.json`, all 24 outputs, exact projected
  inputs, effective instructions, source hashes, and configuration.
- `librarian_assessment/repair-live/` and `repair-offline-checks.json`.
- `reporting-repair/manifest.json`, the refreshed run 14 and run 15 reports,
  and the separately labelled Scene 7 validation reproduction.
- `pytest-followup-full.txt` and `decisions.tsv`.
