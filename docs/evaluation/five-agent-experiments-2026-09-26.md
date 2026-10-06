# Five-agent Scenario: runs 14–15 and role experiments

This is the historical record of the 26 September 2026 work on the
`memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19`
Scenario, adoption identity
`338f48f7dac75f603aed241ce50499a87bc8cfe5ceeb7ea27daa51322b5a2a81`. The
Backstory, Ground truth, and adoption were not edited. Current status and next
steps are in
[the baseline and Sculptor options](five-agent-baseline-and-sculptor-options-2026-09-26.md).

In summary:

- Full runs 14 and 15 passed 7 and 6 of 9 Scenes on automated checks, on the
  same code and model settings. Every connection hard pass had a semantic
  defect, and one contained a wrong attribution introduced by Provenance.
- Two application changes were retained: direct presentation of requested
  connections, and a required attempt on every requested public page.
- Librarian now receives structural validation errors inside its repair loop.
- Reports now separate automated grades, semantic review, and execution
  failures.
- No reviewer change fixed the recorded wrong speaker attribution. Instruction,
  reasoning-effort, and single-claim variants were all left unadopted.

All experiments used `openai:gpt-6-luna` with low reasoning unless stated.
Inputs were frozen within each comparison. Small samples show observed
differences, not proven causes.

## Full runs 14 and 15

| Scenes | Run 14 hard checks | Run 15 hard checks |
| --- | --- | --- |
| 1 through 5: curation | All passed | All passed |
| 6: requested comparison | Failed | Passed |
| 7: challenge the stronger claim | Passed | Failed |
| 8: discover a useful connection | Failed | Failed |
| 9: resist the excuse about a promise | Passed | Failed |

Traces are in Logfire for
[run 14](https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_curation_and_cross_source_connection/compare?experiment=01a0dde95a1d7a5a85a51704c5c97701-7d364f9091eca7b5)
and
[run 15](https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_curation_and_cross_source_connection/compare?experiment=01a0ddeef4d499f79c333db7aab28f7a-1bade04b286f4eb2).

**Run 14**

- Scene 9 is a false pass. Muse correctly assigned the lateness excuse to
  Pinocchio. Provenance told Muse to attribute it to Lamp-Wick, then approved
  the incorrect revision. The canonical line "Poor Pinocchio! And if the Fairy
  scolds you?" makes the actual speaker clear.
- Scene 7 passed hard checks but omitted Hume's introspection claim and
  Keller's completed-examinations context.
- Scene 6 gathered all six required records and opened the Hume page, then
  ended in a safe decline after two reviews. The reviewer objected to supported
  interpretations, such as Alice expressing a changed sense of self. Muse also
  left real gaps: an unmapped comparison summary, the continuing hosting
  intention, Keller's completed examinations, and Hume's introspection claim.
- Scene 8 again chose the identity comparison over the postponement comparison
  and lacked the required earlier Pinocchio promise record.

**Run 15**

- Scene 6 passed hard checks with the same Hume and Keller omissions, though it
  kept the reader's intention to host.
- Scene 7 lost all book evidence: Librarian added a requested part using
  invented reader wording, and the final application check rejected the
  assessment without returning the error to the model. The assessment also
  selected Keller's college passage while describing her lake passage, which
  was in its input. A valid source ID does not establish that its explanation
  matches the passage.
- Scene 8 selected an identity comparison, this time using Keller.
- Scene 9 failed during Muse output repairs: overlapping claims and limits,
  quotation copying, and reader-directed text inside a book-source mapping. The
  grade recorded `provider_failure`, but the exchange shows
  `model_response_error` with no HTTP failure.

Neither run recorded an HTTP provider failure. The requested Hume page opened in
all four source-gathering Scenes.

## Retained application changes

- **Direct presentation.** An explicit reading-connection request is shown
  directly. The previous policy asked permission to show a connection the
  reader had already requested. Unsolicited connections still need an
  invitation.
- **Requested pages.** Source gathering accounts for every supplied public URL.
  For a source identified as requested, it must record a real, permitted
  `get_page` attempt before returning or declaring the source unfound. The model
  still decides whether an indirect reference names that source.
- **Librarian repair loop.** Validation is shared between the bounded retry
  loop and the final application check: selected records, requested-part
  support, exact reader wording, unknown part indices, and sufficient-coverage
  claims. Final validation stays independent and retry budgets are unchanged.
- **Replay tooling.** The selected-scene runner validates the whole adopted
  Scenario before filtering Scenes. The captured-stage runner repeats Librarian
  request planning, Librarian assessment, and Provenance review with current
  contracts and validators. Commands are in
  [the synthetic evaluation README](../../evals/synthetic_journals/README.md).
- **Reporting.** Reports keep the original hard grade beside a semantic status
  (unreviewed, passed, failed, or inconclusive). Execution diagnostics separate
  HTTP or provider failures, model-output errors, proven repair exhaustion,
  post-call rejection, and other failures. New reports bind review to extracted
  facts and verify artifact hashes; legacy reports stay readable with their
  weaker binding marked.

## Librarian experiments

**Assessment repetitions.** Three repetitions of run 13's Scene 8 assessment
kept all 100 retrieved candidates, about 210,000 characters. Two passed checks
and kept the Pinocchio delay passage. The third also selected it, but claimed
sufficient coverage with one requested part unsupported, and was rejected. One
accepted output assigned a promise to an excerpt that did not contain it. Runs
12 and 13 both retrieved the delay passage; only run 12's assessment passed it
on.

**Repair probes.** Each probe injected a saved faulty response, then used one
real provider response to repair it.

| Saved failure | Repair result | Remaining semantic problem |
| --- | --- | --- |
| Run 13, Scene 8: sufficient coverage omitted a requested part | Returned weak evidence with that part explicitly unsupported; kept selected records | Still described a promise absent from the selected Pinocchio excerpt |
| Run 15, Scene 7: invented reader wording | Replaced it with the exact reader span "Do they?"; kept requests and selected records | Still described Keller's lake passage while selecting her college passage |

Both outputs passed the final guard. This shows the repair path works for the
recorded defects, not how often they occur or whether sources are read
correctly.

## Muse output format experiment

An experimental adapter wrote each segment once and derived exact claim
mappings from that text, keeping the existing candidate checks. Retrieval was
frozen. All three baseline and all three experimental outputs eventually passed
validation; both needed repair on every first attempt. The experimental format
used 6 provider requests against 10.

Inspection found claim-coverage defects in all six replies. Experimental
replies still placed positive book claims in reflection or source-limit
segments, and one baseline reply misstated Hume's location hierarchy.
Production Muse keeps its format.

## Serendipity selection experiment

Both variants used direct presentation and run 12's complete pool, with new
retrieval disabled. The candidate stressed the reader's practical question
without dropping its qualifications. A contrasting authenticity request
explicitly excluded postponement.

| Selection result | Original instructions | Candidate instructions |
| --- | --- | --- |
| Original cue: selected the Pinocchio delay passage | 0 of 3 | 1 of 3 |
| Original cue: selected Alice instead | 3 of 3 | 1 of 3 |
| Original cue: declined | 0 of 3 | 1 of 3 |
| Authenticity contrast | 1 Alice, 1 decline | 1 Alice, 1 decline |

The candidate reduced structural retries but did not reliably improve
relevance. It was not adopted (`linger-d4o4`).

## Provenance experiments

### Permission clarification

Six saved inputs were reviewed three times each with the original instructions
and with a candidate. The candidate said that an existing connection grant
permits its book passage without an active reading session, and that an opened
public page needs no book progress boundary.

| Check | Original instructions | Candidate instructions |
| --- | --- | --- |
| False demand for an active book in run 11, Scene 9 | 1 of 3 | 0 of 3 |
| Full Alice reply in run 11, Scene 6 accepted | 3 of 3 | 2 of 3 |
| Wrong Fairy attribution in run 10, Scene 7 rejected | 3 of 3 | 3 of 3 |
| Keller patchwork paraphrase challenged | 2 of 3 | 0 of 3 |

The candidate was reverted because the controls did not show improved
accuracy. A higher acceptance rate alone cannot qualify a reviewer fix. The
Alice reply also contains an unmapped comparison, so accepting the whole reply
differs from judging its Alice claim.

The Keller paraphrase turned out to be disputed rather than a reliable
negative: the full paragraph links reading to the substance of her mind as well
as to patchwork compositions. It is excluded from binary accuracy claims and
replaced by controls G and H below.

### Reasoning effort

The full review ran at low and medium reasoning on identical inputs, three
times per case. Figures concern the target claim, not the whole verdict.

| Target claim | Low reasoning | Medium reasoning |
| --- | --- | --- |
| Correct Pinocchio speaker accepted | 2/3 | 3/3 |
| Incorrect Lamp-Wick speaker rejected | 2/3 | 2/3 |
| Grounded Alice interpretation accepted | 3/3 | 3/3 |

Medium reasoning still accepted the wrong speaker once and took longer. It was
not adopted.

### Focused single-claim review: controls A to H

An experimental task gave the same Provenance Agent one claim group, its full
canonical passages, and the whole reply for context. It omitted prior findings
and unrelated policy checks, and required literal source excerpts. These cases
are the reviewer controls referenced elsewhere.

| Case | Result across three repetitions |
| --- | --- |
| A: simple correct Pinocchio claim | Correctly accepted 3/3 |
| B: simple wrong Lamp-Wick claim | Correctly rejected 3/3 |
| C: grounded Alice interpretation | Correctly accepted 3/3 |
| D: disputed Keller paraphrase | Accepted 3/3; qualitative only |
| E: original recorded Pinocchio claim | Accepted 2/3; one rejection gave an inconsistent explanation |
| F: recorded revised answer with wrong Lamp-Wick attribution | Incorrectly accepted 3/3 |
| G: Keller's correct "cannot always" statement | Correctly accepted 3/3 |
| H: contradictory "can always" statement | Correctly rejected 3/3 |

The task got all 15 simple binary controls right, then accepted the recorded
wrong revision (F) every time, with explanations that assigned Pinocchio's
dialogue to Lamp-Wick. The canonical dialogue is the same in B and F; the reply
context and claim wording differ, so the cause is not isolated. Clean controls
alone would have falsely qualified this change. Case E also mixes speech and
thought wording, which should be judged separately from speaker identity.

A reviewer change should pass the recorded full-answer failures, not only the
minimal controls, before production adoption.

## Cross-agent impact of the retained changes

- **Muse:** receives requested connections directly and evidence after
  Librarian's bounded repair. Connection, evidence-strength, and revision tests
  cover this.
- **Librarian:** receives structural feedback in its repair loop. Request-plan,
  evidence-strength, and captured-stage tests cover this.
- **Serendipity:** gains the requested-page inventory and attempt checks.
  Source-gathering, book-selection, and connection tests cover this.
- **Provenance:** no production change.
- **Sculptor:** no effect.

## Open at the end of 26 September

- Reviewer speaker attribution (`linger-7etz.3`).
- Librarian support descriptions that do not match the selected passage.
- Requested-content completeness in Scenes 6 and 7.
- Scene 8 choosing identity over promise and delay (`linger-d4o4`).
- Controlled repair work continues under `linger-7etz.1`. `linger-7etz.2`
  (Librarian feedback) and `linger-7etz.4` (reporting) are closed.

Local artifacts were under `/private/tmp/linger-stage-repair-20260926/`, which
is temporary; Logfire holds the durable traces.
