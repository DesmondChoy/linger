# Librarian experiments: results, changes, and failure patterns

Prepared September 24, 2026 from the `librarian-attempts` branch at `09242b4`. This report covers the saved five-book pilot, the expanded investigation, local retrieval probes, and all 21 numbered repair attempts. It analyzes existing records; no new live evaluation was run.

The work improved retrieval coverage, chapter handling, and several release checks. It did not produce an all-pass end-to-end batch. The strongest recorded full batch was attempt 18: 26 of 29 native Scenes and 28 of 32 judgments passed, alongside 12/12 direct retrieval cases, 12/12 answer-release cases, 4/4 claim-mapping controls, and the outside-essay smoke test. Remaining failures mostly involved constructing chapter authority, declaring adequate source support, and obtaining a valid review after revision.

The main lesson is that finding a relevant passage is only one part of a correct answer. A source can be authentic but insufficient for a claim. A passage can answer the question but lie beyond the reader's demonstrated progress. A valid answer can also be rejected by a malformed or overstrict review.

The [design history](design-history.md), also available as an [interactive HTML report](design-history.html), explains how and why the August proposal evolved into the retained architecture, using designs, Beads, commits, and experiments. The [attempt chronology](chronology.md) records what changed in each iteration. The [measurements](measurements.md) give every saved result, recurring failure counts, and reproduction instructions. The [machine-readable aggregate](aggregate.json) includes individual Scene outcomes and hashes of the 403 source JSON files used for the counts.

## Evaluation scope

Five new synthetic scenarios covered every book available in the corpus at the time:

- *Alice's Adventures in Wonderland*
- *Animal Farm*
- *The Adventures of Pinocchio*
- *Narrative of the Life of Frederick Douglass, an American Slave*
- *The Story of My Life* by Helen Keller

Each new scenario contained four Scenes: explicit book grounding, personal reflection without book retrieval, a specific event from which reading progress can be inferred, and an ambiguous event that requires clarification. This added 20 Scenes. Grounded reflection and personal-only Scenes did not need stored memory. Spoiler inference Scenes used authored earlier-reader statements where the objective required them.

Three existing scenarios added nine Scenes: Alice's Pigeon encounter, Alice's gardeners painting roses, and an Alice/Hume cross-source connection. The resulting native set contained 29 Scenes and 32 objective judgments. A Scene can have more than one judgment.

| Suite | Coverage | What it establishes |
| --- | --- | --- |
| Native replay | Eight scenarios, 29 Scenes | Production role handoffs, retrieval, chapter permissions, replies, and release against adopted expectations |
| Direct Librarian | 12 Alice cases from the notebook's real helper functions | Selected evidence, evidence strength, citation resolution, and permitted search scope |
| Answer release | The same 12 Alice cases through `evals/librarian/live_validation.py` | Librarian → Muse → Provenance behavior with explicitly confirmed chapter limits |
| Claim mapping | Four controls, added in attempt 6 | Wrong-record rejection and individual/combined source support |
| Outside-essay smoke | `cross-source-outside-essay-v1.json` | Live external discovery, book grounding, a tentative comparison, and release |

The direct suite executed notebook helpers, not a cell-by-cell Jupyter session. The two 12-case suites use the same small Alice case set; they do not add 24 independent multi-book examples. The smoke exercised live external search, while the saved cross-source scenarios used adopted public-page snapshots. Provenance and sometimes Serendipity appear because native replay tests the actual answer path, even when the objective centers on Librarian and Muse.

Four historical scenarios were excluded at preflight: Caterpillar, kitchen, and quotation needed schema migration; Alice identity connections lacked independent adoption. Those ten Scenes are missing coverage, not passes or runtime failures. [Initial scope and preflight evidence][initial-investigation]

## Results and the usable baseline

The five-book pilot passed 14/20 Scenes. It exposed an unsafe Chapter 26 grant for Pinocchio and unnecessary clarification for specific Alice, Douglass, and Keller stopping events. After focused retrieval changes, the expanded investigation passed 17/29 Scenes and 19/32 judgments. All five specific stopping points could now be inferred, but three ambiguous descriptions still led to unsafe plot disclosure. Better retrieval alone had not solved permission. [Pilot][pilot] · [Expanded investigation][initial-investigation]

The numbered repair series contains 21 attempts, not 20. The original limit was extended once after suspected exhausted API credit. Six attempts reran selected subsets; attempt 15 was interrupted. All other attempts selected the complete suite set available at that stage. The mapping suite was added in attempt 6, whose result was ungraded after diagnostic serialization failed. A completed budget reservation does not mean every requested evaluation completed. [Run ledger][budget]

| Measurement | Attempt 1 | Attempt 18, selected checkpoint | Attempt 20, quota affected | Attempt 21, extra rerun |
| --- | --- | --- | --- | --- |
| Native Scenes | 17/29 | 26/29 | 2/29 | 23/29 |
| Native judgments | 17/32 | 28/32 | 2/32 | 25/32 |
| Strict direct retrieval | 11/12 | 12/12 | 4/12 | 12/12 |
| Strict answer release | 11/12 | 12/12 | 0/12 | 11/12 |
| Claim mapping | Not run | 4/4 | 1/4 | 4/4 |
| Outside-essay smoke | Fail | Pass | Fail | Pass |

“Strict” requires every case-level check used by the batch driver. An aggregate target can pass while an individual case fails. Earlier release summaries sometimes met their average targets despite missing evidence or an incorrect strength label in one case. Native results and component rates should remain separate.

Attempt 18 provides a concrete historical reference:

| Observed measure | Attempt 18 |
| --- | --- |
| Native Scene pass rate | 89.7%, 26/29 |
| Native judgment pass rate | 87.5%, 28/32 |
| Direct mean evidence recall, precision, and strength accuracy | 100% on the 12 saved cases |
| Direct latency | Mean 8.70 s; median 8.66 s; observed range 5.54–13.90 s |
| Release mean latency | 34.16 s |
| Release reported p95 latency | 68.12 s across 12 cases |
| Release recorded usage | 796,503 input tokens; 30,069 output tokens; 83 requests |
| Boundary review | Five correct specific-event grants and six safe ambiguous controls; no unauthorized ceiling or disclosure found in 23 book-flow Scenes |
| Recorded HTTP 429 | None observed |

Latency and usage belong to the named component only, not the full batch. Bounded repairs can make several requests for one case. The p95 is a small-sample descriptive statistic, not a service guarantee. [Direct results][direct18] · [Release results][release18] · [Boundary review][boundary18]

This is a selected historical checkpoint, not an established “normal range.” Each changing configuration was generally sampled once. Code, prompts, expectations, reasoning effort, and concurrency changed during the series. The best observed run is subject to selection bias. Attempt 18's live results also do not freshly validate the later rebased implementation. [Checkpoint record][checkpoint]

Attempts 20 and 21 are the closest availability comparison: all 222 manifest entries matched except the budget-driver change permitting attempt 21. The runtime, model, and adopted inputs were fixed. Native results recovered from 2/29 to 23/29 when observed 429 errors disappeared. This supports an availability explanation for much of attempt 20's collapse; it does not prove the account's billing cause. Six native failures remained after availability recovered. [Attempt 21 review][review21]

## Changes, with before and after examples

### Chapter identity and inclusive search permission

**Before.** Physical section numbers were easy to confuse with literary chapters. Keller's edition starts with a dedication and an editor's preface. Its `sec003` is Part I Chapter 1, `sec011` is Chapter 9, and `sec012` is Chapter 10. The horseshoe-crab passage in `sec012` is therefore correctly Chapter 10 evidence. Douglass's Chapter 7 is similarly stored in section 10.

**After.** Canonical chapter and section metadata resolves the literary chapter independently of storage numbering. A separate handoff repair also preserves inclusive permission. Previously Muse turned an inferred completed Keller Chapter 10 into a `started` Chapter 10 search, which deliberately searches only through Chapter 9. Pigeon similarly became Chapter 4 after a correct Chapter 5 inference. The application now supplies the validated scope while Muse supplies search intent. [Keller source audit][keller-audit] · [Scope investigation][initial-investigation]

### Focused queries with protection against omitted requests

**Before.** A reader message could combine progress, a quotation request, literary interpretation, and personal reflection. Searching the whole message made irrelevant wording compete with the book question. Classifying each clause too aggressively also risked dropping a genuine book request.

**After.** The planner creates focused book needs, retains uncertain needs, and also searches the original reader request. Earlier reader statements remain available where progress inference requires them. Evidence assessment checks completeness against the original message.

For example, the saved Farm request describes Snowball's expulsion, identifies the dogs as the puppies, describes the windmill reversal, asks for Squealer's two leadership sentences, and relates this to a project lead. A useful conceptual split is “dogs and earlier puppies,” “windmill reversal and final stopping event,” and “leadership quotation and loss of decision-making.” The workplace feelings inform the response rather than supply a book fact. This split illustrates the design; it is not a verbatim planner transcript.

If decomposition misses the puppy-recognition request, searching the original message gives that evidence another route into the candidate set. This reduces one false-negative risk but does not guarantee recall. Ranking can still remove a candidate, and a need discovered during assessment does not automatically trigger another search. [Saved Farm input][farm18] · [Recall protection and limits][initial-investigation]

### Private candidate retention and long-passage reranking

**Before.** Keller's ambiguous lost-pet description could refer to the canary or the crab. The canary passage reached fusion rank 4, then reranker rank 12 of 15 with a score of 0.000558799. The five-record private selection dropped it. A single remaining plausible episode could then look more certain than the reader's wording justified.

**After.** The private path preserves independent lexical and semantic candidates within a 20-record budget. A cached probe retained 18 records, including both crab and canary. This broad private evidence pool does not itself authorize disclosure.

Separately, the reranker previously truncated query/passage pairs at 512 tokens. The wrapper now scores overlapping windows and associates the maximum score with the unchanged canonical passage. A 1,022-token probe used three windows, allowing the ending to be scored. Its raw score moved from −10.546 to −9.193 and remained low. That proves tail coverage, not that windowing solved relevance. The probe did not establish that truncation caused the canary's low score. Retrieval fusion ranks and reranker scores also measure different things; their numerical scales are not interchangeable. [Retrieval design][retrieval-design] · [Probe][retrieval-probe]

### Chapter authorization independent of a plausible match

**Before.** The boundary model could confidently select a genuine event without enough reader evidence to distinguish it. Pinocchio's vague school detour became Chapter 26 even though Chapter 9 was also plausible. Earlier Douglass and Keller runs likewise disclosed later plot. Typed evidence and high confidence did not make those grants safe.

**After.** Repairs made uncertainty a distinct output shape, checked the complete candidate inventory, and bound private proof excerpts to the cited records. Attempt 15 added a separate current-event identification call. It sees the original reader wording and canonical candidates without the proposed ceiling or earlier model judgment. Agreement is required before access is granted.

Attempt 18's boundary review found correct grants and safe clarification controls. However, none of those live controls exercised a rejection by the new second gate: they were already uncertain before that gate. The new rejection path remains an explicit coverage gap. [Boundary design][boundary-design] · [Boundary review][boundary18]

### Exact quotations, source attribution, and combined support

**Before.** Authentic citations could support only part of a sentence. Roses said the concealment failed but mapped that claim to the earlier gardeners' intention, while the discovery passage was elsewhere. Other replies used stored reader facts without declaring memory evidence. Reviewers also invented quotation mismatches or incorrectly required each individual source to prove a whole combined claim.

**After.** The release checks inspect quotation equality, source-specific contributions, combined support, and uncovered reply claims. Source indices reduce copying errors. Bounded repair feedback identifies exact defects, and revisions must preserve still-supported content and reader attribution.

The four mapping controls reached 4/4 in attempt 18, but that does not establish reliable first-pass review. The wrong-record control needed a literal-source guard and a second request to reject an initial approval. Native Pinocchio still passed with an undeclared source-dependent interpretation. These checks improved detection without eliminating semantic mistakes. [Initial source-mapping investigation][cross-investigation] · [Mapping review][mapping18]

### Evaluation corrections and observability

**Before.** Exact support-set equality rejected extra valid in-boundary passages. The Alice identity case insisted on weak evidence even when Chapter 5 directly supported a qualified interpretation of size and identity. Separate runner defects omitted the reader's actual message from Provenance, rejected normalized blank lines in canonical citations, and lost mapping diagnostics during serialization.

**After.** Explicitly approved changes admitted reviewed optional spoiler evidence while retaining required anchors and ceilings. Alice Chapter 5 alternatives became valid for the qualified identity interpretation. Runner fixes supplied the current message, respected canonical citation resolution, recorded transcripts and provider errors, and distinguished proposed private proof from granted support.

Expectation changes are part of the score improvement and must be reported separately from runtime fixes. They began in attempt 14; another approved identity anchor followed in 17 and optional Douglass evidence in 20. Roses' corrective-evidence allowlist change was still pending. No report should retroactively relabel the original grades. [Expectation record][expectations] · [Chronology](chronology.md)

An earlier release attempt stopped before any provider call because the introduction was parsed as the title “Alice's Adventures in Wonderland, and I've completed.” The runner initially moved the completed chapter before the title. The subsequent repair ledger records the title-parser bug as fixed. Early usage reporting also returned unavailable values because it called an SDK usage property as a method; later accounting was repaired. Those missing historical values are not zero and cannot support a before/after cost comparison. [Initial standalone diagnosis][standalone] · [Verified-fix ledger][decisions]

## Aggregate failure patterns

The numbered archive contains 482 saved native Scene observations, with 337 mechanical passes and 145 failures. It covers 135 scenario runs, including recovered Pigeon evidence from interrupted attempt 15. Missing outcomes are excluded. Attempt 20 contributes 27 failures; excluding that batch leaves 118 failures among 453 observations. Neither fraction estimates production reliability because known failures were rerun more often and the implementation changed.

The most persistent failures were concentrated in a few Scenes:

| Scene | Failed / observed attempts | Repeated problem |
| --- | --- | --- |
| Roses connection, S1 | 19/20 | Missing or incorrect source mapping, review failures, and corrective evidence outside the adopted allowlist |
| Roses restraint, S2 | 18/20 | Defensible evidence-limit statements rejected, combined support errors, and release fallback |
| Farm spoiler inference | 16/16 | Mandatory puppy-to-dog recognition evidence absent, even when the final Chapter 5 event was identified |
| Pinocchio spoiler inference | 12/16 | Support-set mismatch and boundary-output or review failures |
| Alice event-led spoiler inference | 10/15 | Boundary-output failures, proof mismatch, and unsuccessful review |
| Pigeon reflection | 10/18 | Boundary and quotation/release defects |
| Douglass spoiler inference | 9/14 | Malformed inventory, wrong-record proof, or incompatible chapter support |

These totals preserve historical labels; they do not imply each recurrence had the same cause. Farm's persistent failure cannot be fixed merely by admitting extra passages: its adopted recognition anchor was still missing in later runs. However, the saved proof review found that prior knowledge plus the uniquely identified final event can establish the correct Chapter 5 ceiling without citing that intermediate bridge. Whether all three anchors are essential remains an expectation decision. The omission does not by itself show unsafe permission. [Farm proof review][farm-proof]

Scene-deduplicated failure codes reinforce the distinction between stages. `boundary_support_differs_from_ground_truth` appears 57 times. `provenance_did_not_pass_release` and `response_not_released_from_allowed_source` each appear 44 times. `required_grounding_evidence_not_retrieved` appears nine times, six during attempt 20. A failed grant can generate several later failures, so these counts overlap. The nine retrieval flags do not measure all retrieval defects; boundary retrieval loss can appear under other codes. [Full incidence tables](measurements.md)

The recurring patterns are:

1. **Evidence found, authority construction fails.** Valid passages do not become accepted boundary proof because of missing IDs, duplicate inventory entries, wrong-record excerpts, or a missing continuity anchor. Safe fallback avoids disclosure but produces an unnecessary refusal.
2. **More recall exposes more ambiguity.** Recovering alternative passages is useful, but the authorization step must account for them. A higher relevance score cannot grant reading permission.
3. **Authenticity passes while support fails.** A quote can be exact and a citation resolvable while the reply assigns the wrong speaker, omits a source-dependent claim, or treats reader-reported information as established fact.
4. **Review repair creates a new error.** Fixing quotation formatting can remove a required quotation, alter speaker attribution, drop another accepted source mapping, or produce a new invalid audit member.
5. **A grading mismatch can resemble a product defect.** Additional verified evidence and valid alternative interpretations caused false negatives. However, removing mandatory evidence requirements would conceal real defects.
6. **Execution failures create cascades.** Quota errors, content filtering, invalid structured output, and interrupted processes need separate labels. A content-filtered review is not evidence of absent corpus support.

Archived AI-assisted artifact reviews classify the same 482 observations as 228 credible passes, 95 passes with limitations, 14 potential false positives, 32 potential false negatives, 71 supported failures, 36 inconclusive, and six not exercised. These are interpretive review labels, not independently adopted human ground truth. They show why automated counts alone are insufficient. For attempt 18 specifically, the review found 17 credible passes, eight limited passes, one potential false positive, one potential false negative, and two supported failures. [Saved review labels](measurements.md) · [Attempt 18 review][review18]

## What remains open in the recorded experiments

| Issue | Concrete failing example | Next verification |
| --- | --- | --- |
| Boundary inventory reliability | Attempt 18 Douglass repairs a wrong-record excerpt but then duplicates an inventory entry. Attempt 21 adds Chapter 10 support while proposing Chapter 7. | Valid copybook inference plus adversarial malformed inventories, without granting incompatible scope |
| Required continuity evidence | Farm identifies the Chapter 5 windmill reversal but omits the adopted passage recognizing the dogs as the earlier puppies. | Review whether the intended contract requires that intermediate bridge, then test the agreed proof requirement; preserve the recorded failure meanwhile |
| Roses expectations and mapping | Corrective discovery evidence contradicts the reader's premise but lies outside the adopted allowlist; a source-limit conclusion can also remain unmapped. | Independently review the expectation proposal, then verify every combined claim against its declared records |
| Semantic false approvals | Attempt 18 Pinocchio leaves an interpretation undeclared. Attempt 21 attributes “Explain yourself!” to Alice and treats a project lead's reported burden as fact. | Speaker, attribution, and undeclared-interpretation controls in complete replies |
| Proof representation | Attempt 21's rabbit case needs clauses spanning 899 source characters, while one proof excerpt is limited to 800. A separate riverbank detail is unsupported. | Permit adequate multi-span proof or split claims while retaining rejection of genuinely unsupported details |
| Complete workflow success | Attempt 21 Keller releases a usable exact answer but has an extra failed grounding call and malformed Serendipity output. | Grade final-answer quality and unnecessary failing calls separately |
| Boundary negative-path coverage | Later ambiguous controls clarify before the independent event gate rejects a proposal. | Demonstrate that the second gate blocks a plausible but unjustified first-stage grant |

Farm's attempt-18 reply also failed release after a content-filtered Provenance repair. That execution failure is separate from the missing puppy-recognition evidence; a successful retry alone would not repair the missing anchor.

These are historical unresolved findings, not a new verification of today's application. Existing tracking at the checkpoint included `linger-9oqp`, semantic review `linger-9oqp.18`, proof representation `linger-9oqp.20`, and expectation review `linger-42d3`. This reporting work does not close them. [Checkpoint][checkpoint] · [Attempt 21 details][review21]

## Conclusions for the next experiment

The evidence supports keeping broad private retrieval, application-owned chapter permission, canonical source identities, and explicit source-support checks. It does not support lowering a relevance threshold as a general solution, treating confidence as permission, or counting structural passes as complete semantic validation.

The next useful baseline would freeze one runtime manifest, one adopted dataset version, the model settings, and concurrency. Repeat that exact configuration several times and report variability by Scene and stage. Record availability separately, preserve first-pass and post-repair outcomes, and audit both passes and failures. Add held-out wording and new book events before treating improvements on these repeatedly inspected 29 Scenes as generalization.

The prepared Luna-versus-Sol comparison was never run live. Luna high reasoning was tried in attempts 9 and 10, then returned to medium; changing prompts and provider failures prevent a clean model-effort conclusion. Lower concurrency also did not establish a causal fix for 429 errors. These remain hypotheses rather than proven improvements. [Experiment chronology](chronology.md)

For retention, preserve the source manifests, adopted inputs, result artifacts, and the semantic reviews linked here. Hash manifests identify inputs but do not reconstruct deleted file contents. The aggregation script regenerates counts without provider calls; it cannot recreate missing live transcripts or establish remote Logfire availability. No experiment was rerun, no production behavior was changed, and no commit or push was made for this report.

[pilot]: ../../../synthetic-journal-evaluation/reports/five-book-replay-2026-09-17/evaluation-report.md
[initial-investigation]: ../../../synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/investigation.md
[budget]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/live-budget.json
[checkpoint]: ../../iteration-18-checkpoint.md
[direct18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/suite-direct.json
[release18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/suite-release.json
[boundary18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/boundary-analysis.md
[keller-audit]: ../../corpus/story-of-my-life-source-audit.md
[farm18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/suite-7.json
[farm-proof]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/farm-proof-review.md
[retrieval-design]: ../../../reports/librarian-fixes-2026-09-17/design-retrieval.md
[retrieval-probe]: ../../../reports/librarian-fixes-2026-09-17/retrieval-probe.json
[boundary-design]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-15-boundary-design.md
[cross-investigation]: ../../../synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/investigation-cross-source.md
[mapping18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/component-mapping-smoke-analysis.md
[expectations]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/expectation-review.md
[review18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/review-summary.md
[review21]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-21-f155ea01/review-summary.md
[standalone]: ../../../synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/standalone/analysis.md
[decisions]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/decisions.tsv
