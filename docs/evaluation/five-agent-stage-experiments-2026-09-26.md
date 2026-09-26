Two more complete runs still did not produce a complete nine-scene pass.
Seven Scenes passed their automated checks in run 14 and six in run 15, on the same production
code and model settings. One green result contained a wrong attribution
introduced by the reviewer. We also repaired two application behaviors and
completed 55 focused role invocations using 81 provider requests, including
validation retries. The full Scenario runs are additional to those counts.

This work follows the 13-run analysis for the adopted
`memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19`
Scenario. The adoption identity remains
`338f48f7dac75f603aed241ce50499a87bc8cfe5ceeb7ea27daa51322b5a2a81`.
The Backstory, Ground truth, and adoption files were not edited.

The [follow-up repair report](five-agent-followup-repairs-2026-09-26.md) records
the subsequent Librarian validation repair, reporting changes, and reviewer
accuracy experiments. The results below describe the earlier stage experiments
and full runs.

Follow-up calibration corrected one interpretation below: the Keller patchwork
paraphrase is disputed rather than a reliable binary negative. The full excerpt
connects reading with the substance of her mind as well as the patchwork of her
compositions. Its acceptance alone does not establish a reviewer error. The
subsequent experiment retains this case and adds an explicit can/cannot
contradiction against her statement about distinguishing her thoughts from
those she has read.

Six saved Provenance inputs were each reviewed three times with the original
instructions, then three times with a proposed permission clarification. All
36 review invocations used the configured `openai:gpt-6-luna` model with low reasoning
effort. Inputs and recorded histories were identical across the comparison.
Validation retries produced 45 provider responses, 23 in the baseline and 22
in the candidate. The baseline recorder encountered a usage-reporting error
after saving valid outputs. Its original artifacts retain that failure status.
`provenance/baseline/validated_summary.json` records the recovered validation
results. No additional model calls were needed to recover them.
The candidate clarified that an existing connection grant permits its book
passage without a separate active reading session. It also clarified that an
opened public page needs no book progress boundary.

| Check | Original instructions | Candidate instructions |
| --- | --- | --- |
| False demand for an active book in run 11, Scene 9 | 1 of 3 reviews | 0 of 3 reviews |
| Full Alice reply in run 11, Scene 6 accepted | 3 of 3 reviews | 2 of 3 reviews |
| Wrong Fairy attribution in run 10, Scene 7 rejected | 3 of 3 reviews | 3 of 3 reviews |
| Keller patchwork paraphrase specifically challenged | 2 of 3 reviews | 0 of 3 reviews |

The candidate accepted the Keller answer outright twice. Its third review
objected to a separate compound-limit problem. This is an observed decision
change; the later calibration means it is not proof of worse semantic accuracy.
The full Alice reply also contains an unmapped comparison, so its overall
acceptance is distinct from the accuracy of its Alice claim. We reverted the candidate because the
controls did not establish improved accuracy. These small samples do not prove
that the prompt caused every difference. They do show why a higher acceptance
rate alone cannot qualify a reviewer fix. The original reviewer also missed
some speaker attribution defects, so reverting the candidate does not resolve
reviewer reliability.

The retained application changes address failures with direct regression
evidence:

- An explicit reading-connection request now receives direct presentation.
  The prior application policy asked permission to show a connection that the
  reader had already requested. An unsolicited connection still requires that
  invitation.
- Source gathering now accounts for every supplied public URL. For a source
  identified as requested, it must record a real, permitted `get_page` attempt
  before returning or declaring the source unfound. A supplied URL can remain
  unopened when the reader did not request it. The model still decides whether
  an indirect reference names that source. The new check cannot prove that
  every such reference will be recognized correctly.

The selected-scene runner validates the complete adopted Scenario before
filtering Scenes. The captured-stage runner can repeat Librarian request
planning, Librarian evidence assessment, and Provenance review using current
production contracts and validators. It records original and projected input
hashes, code and model identities, transcripts, and failure categories. A
valid review that rejects an answer counts as a completed agent call, not a
successful answer. Commands are documented in
[the synthetic evaluation README](../../evals/synthetic_journals/README.md).

An experimental Muse adapter writes each segment once and derives its exact
claim mappings from that text. It retains the existing Muse candidate checks.
The comparison froze retrieval and exposed no new tools. All three baseline
outputs and all three experimental outputs eventually passed mechanical
validation. Baseline repetitions used 10 provider requests, compared with six
for the experimental format. Both formats required repairs on every first
attempt.

Independent inspection found claim-coverage defects in all six replies.
The experimental replies still placed positive book claims in reflection or
source-limit segments. Baseline replies had similar mapping gaps. One also
misstated Hume's location hierarchy. Fewer requests do not establish better
answers, so production Muse retains its existing format. The experimental
adapter remains available for further measurements.

Selection evidence also exposed a separate Librarian evidence-selection
problem. Both runs 12 and 13 retrieve the relevant Pinocchio delay passage.
Run 12 passes it to Serendipity. Run 13's Librarian assessment drops it and
passes the invitation passage instead. Serendipity cannot select evidence
that Librarian withheld. The prepared selection experiment therefore
uses the complete run 12 pool, plus a contrasting request about authenticity
that explicitly excludes postponement.

The selection experiment used direct presentation and the same recorded pool
for both variants, with new retrieval disabled. Each variant ran three times
on the original cue and twice on the authenticity contrast. Ten invocations
used 16 provider requests, with no provider errors.

| Selection result | Original instructions | Candidate instructions |
| --- | --- | --- |
| Original cue: selected the actual Pinocchio delay passage | 0 of 3 | 1 of 3 |
| Original cue: selected Alice instead | 3 of 3 | 1 of 3 |
| Original cue: declined | 0 of 3 | 1 of 3 |
| Authenticity contrast | 1 Alice, 1 decline | 1 Alice, 1 decline |

The candidate emphasized the reader's practical question without discarding
its qualifications. It reduced structural retries but did not reliably
improve relevance. Production discovery instructions remain unchanged.

Three separate repetitions of the original run 13 Librarian assessment kept
all 100 retrieved candidates, including the 20 Pinocchio candidates. Two
passed the application checks and retained the delay passage. The third also
selected the delay passage, but claimed sufficient coverage while leaving one
requested part unsupported. The application correctly rejected that output
after the model call. One accepted output still assigned a promise to an
excerpt that did not contain it. The saved input contains about 210,000 characters.
Its size is a reason to test a smaller review task, not proof that input size
caused these errors.

Run 14 passed the hard checks for seven of nine Scenes. Scenes 1 through 5, 7, and 9 passed;
Scenes 6 and 8 failed. The recorded code and model identities were unchanged.
Scene 9's result is misleading. Muse originally assigned the lateness excuse
to Pinocchio. Provenance incorrectly instructed Muse to attribute it to
Lamp-Wick, then approved that incorrect revision. The canonical dialogue
includes "Poor Pinocchio! And if the Fairy scolds you?", making the actual
speaker clear. The released answer therefore contains a false attribution
despite passing every hard check.
The saved trace contains the [incorrect review finding](/private/tmp/linger-stage-repair-20260926/full/run14/evaluation.json:17547),
[resulting revision](/private/tmp/linger-stage-repair-20260926/full/run14/evaluation.json:17837),
and [approval](/private/tmp/linger-stage-repair-20260926/full/run14/evaluation.json:18373).

Run 14's Scene 6 gathered all six required records and opened the supplied Hume
page. It ended in a safe decline after two reviews. The reviewer objected to
supported literary interpretations, including Alice expressing a changed
sense of self. Muse also left genuine gaps: an unmapped comparison summary,
the continuing hosting intention, Keller's completed examinations, and Hume's
introspection claim. Scene 8 again selected the identity comparison over the
postponement comparison. It also lacked the required earlier Pinocchio promise
record. Direct presentation worked, but did not fix evidence selection.

| Scenes | Run 14 hard checks | Run 15 hard checks |
| --- | --- | --- |
| 1 through 5: curation | All passed | All passed |
| 6: requested comparison | Failed | Passed |
| 7: challenge the stronger claim | Passed | Failed |
| 8: discover a useful connection | Failed | Failed |
| 9: resist the excuse about a promise | Passed | Failed |

Run 14's Scene 7 also omits the required Hume introspection claim, even though
its hard checks pass. Its final answer instead describes successive
perceptions and identity attribution. Keller's completed-examinations context
is missing, although the answer does not claim she abandoned duties. These
omissions reinforce the need to inspect meaning separately from citations.

Run 15's Scene 6 has the same Hume and Keller omissions despite passing its
hard checks. It does preserve the reader's continuing intention to host.
Scene 7 loses all book evidence when Librarian adds a requested part using
invented reader wording. The final application check correctly rejects the
assessment, but the model never receives that error for repair. Offline
validation reproduced the rejection. Separately, the assessment selects a
Keller passage about college work while describing the different lake passage,
which was available in its input. A valid source ID does not establish that
its accompanying explanation matches the passage.
The saved trace shows the [invented reader span](/private/tmp/linger-stage-repair-20260926/full/run15/evaluation.json:8117)
and the [empty book result](/private/tmp/linger-stage-repair-20260926/full/run15/evaluation.json:7773).

Run 15's Scene 8 again selected an identity comparison, this time using Keller,
instead of the required promise-and-delay connection. Scene 9 failed during Muse's
output repairs on overlapping supported claims and limits, quotation copying,
and reader-directed text inside a book-source mapping. Its grade contains
`provider_failure`, but the recorded exchange identifies `model_response_error`
with no HTTP failure. This is a model-output failure, not evidence of an API
outage. Neither complete run recorded an HTTP provider failure.

The requested Hume page was opened in all four source-gathering Scenes across
the two runs, with the indirect reader reference recorded in each inventory.
The direct-presentation policy also ran for discovery requests. Those behaviors
worked in these runs, but neither guarantees complete or accurate answers.

The complete traces are available in Logfire for
[run 14](https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_curation_and_cross_source_connection/compare?experiment=01a0dde95a1d7a5a85a51704c5c97701-7d364f9091eca7b5)
and
[run 15](https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_curation_and_cross_source_connection/compare?experiment=01a0ddeef4d499f79c333db7aab28f7a-1bade04b286f4eb2).
Their local artifacts are `full/run14/evaluation.json` and
`full/run15/evaluation.json` under the evidence directory below.

The full offline suite reported 2,511 passing tests and 6,379 passing subtests.
Seven tests failed because the sandbox prevented their temporary local HTTP
server from binding. Their entire 41-test file passed outside the sandbox.
The final Muse adapter checks passed all eight tests after fixing direct
Librarian evidence parsing. The expanded Serendipity checks passed 208 tests
and 76 subtests. `git diff --check` passed.

Cross-agent effects are bounded. Muse receives the corrected connection
presentation policy, covered by the connection and Muse integration tests.
Librarian has no production behavior change. Serendipity gains the requested
page inventory and attempt checks, covered by source-gathering, book-selection,
and connection tests. Provenance has no production behavior change after the
candidate was reverted. Sculptor has no effect.

The live work received specific payload approval after two blocks.
Automatic approval review rejected both attempts to start the selection
experiment, citing the saved cues and evidence sent to `api.openai.com`.
The user then explicitly approved the synthetic Scene 8 and Scene 9 inputs and
up to two full replays. Both full replays are complete. The next experiment
should target reviewer accuracy on the now-proven correct and incorrect
speaker variants, with the Alice and Keller controls retained. Compare a
smaller source-claim review task or a different reasoning budget while keeping
the evidence fixed. Do not add another general instruction paragraph and
infer improvement from a higher acceptance rate.

Librarian's incomplete-coverage and exact-reader-span checks can separately
run inside the existing bounded repair loop, while remaining at the final
application boundary.
That change affects Librarian and the evidence Muse and Serendipity receive;
the request-plan, assessment, and connection tests cover those consumers.
Provenance's review contract and Sculptor have no effect from that repair.
A future reviewer-task experiment affects Provenance's judgments and Muse's
revisions, requiring both source-attribution controls and revision tests.
Librarian, Serendipity, and Sculptor have no direct behavior change from that
experiment. Any broader rollout still needs the unchanged full Scenario.

The evaluation report also needs a separate account of semantic completeness
and error type. An HTTP failure, exhausted output repairs, a discarded evidence
bundle, and an incorrect released answer require different remedies. Preserve
the adopted hard grades and add the semantic findings alongside them; do not
change Ground truth to make these runs pass. This reporting change has no
effect on the production behavior of Muse, Librarian, Serendipity, Provenance,
or Sculptor. Saved run 14 Scene 9 and run 15 Scenes 6, 7, and 9 provide the
regression cases.

Local evidence is in `/private/tmp/linger-stage-repair-20260926/`. The reviewer
comparison is `provenance/comparison.json`, with full inputs and outputs under
`provenance/`. `decisions.tsv` records accepted and rejected changes. Beads
`linger-7etz.1` remains in progress. `linger-7etz.2` tracks returning incomplete
Librarian coverage and invalid reader spans to its repair loop. `linger-7etz.3` tracks false source
attributions introduced by Provenance. `linger-7etz.4` tracks accurate failure
classification and a separate semantic review record. The existing `linger-d4o4` now includes
the negative selection experiment. No commit, push, or remote sync was run.
