# Librarian experiment chronology

This reference accompanies the [analysis report](report.md) and [result table](measurements.md). “Before attempt” identifies the change being tested, not a proven explanation for the result. Several changes landed together. The series does not isolate the causal effect of each intervention.

The numbered history ran September 17–18, 2026. Every numbered attempt used `openai:gpt-5.6-luna`. Attempts 9 and 10 used high reasoning; the documented configuration otherwise used medium. Early summaries omit some settings, so the [decision ledger][decisions] supplies that context. Full native coverage means 29 Scenes. A complete selection initially had 11 suites and grew to 12 with mapping controls. Most early `repair-N-design.md` files describe fixes after attempt N, for the following attempt.

## Work before the numbered repair series

| Experiment | What was tried | Outcome and limit | Evidence |
| --- | --- | --- | --- |
| Five-book generation and review | Four Scenes per book across all five available titles; canonical section resolution; independent adoption | Twenty adopted Scenes. Grounded reflection does not require memory; progress/ambiguity fixtures remain separate. | [Pilot report][pilot] |
| First five-book replay | One production replay per book | 14/20 passed. Unsafe Pinocchio Chapter 26 disclosure; three specific events clarified unnecessarily; some support-set false negatives. | [Pilot report][pilot] |
| Focused retrieval and broader investigation | Focused requests plus original-query fallback; existing Pigeon and cross-source scenarios; notebook and release components; outside-essay smoke | Expanded investigation 17/29 Scenes, 19/32 judgments. Correct specific events were found, but ambiguity and downstream handoffs remained unsafe. Earlier completed runs were reused, not counted as fresh repeats. | [Combined investigation][investigation] |
| Local strategy benchmark | 12 cases × five retrieval strategies × three repetitions | 180 searches. Selected hybrid reranking; recorded 91.67% recall and 82.64% candidate precision, below the candidate precision target. These are retrieval metrics, not final answer quality. | [Standalone analysis][standalone] |
| Cached candidate-retention probe | Preserve lexical and semantic candidates through private selection | Both Keller crab and canary retained in an 18-record result, within a 20-record budget. One reproduced case, not a broad recall estimate. | [Retrieval probe][probe] |
| Long-pair reranker probe | Score overlapping windows under a 512-token pair limit | A 1,022-token pair used three windows. The score remained low. Tail coverage was demonstrated; a semantic-relevance cure was not. | [Retrieval design][retrieval-design] |

The local strategy benchmark recorded these results. Its implementations do not exercise production request decomposition or final evidence assessment. The three repetitions measure latency, not repeated model reliability. [Saved benchmark analysis][standalone]

| Strategy | Recall | Candidate precision | Retrieval support-label accuracy | Warm p95 latency |
| --- | --- | --- | --- | --- |
| Direct | 50.00% | 16.25% | 66.67% | 6.53 ms |
| BM25 | 75.00% | 28.33% | 91.67% | 5.51 ms |
| Semantic | 79.17% | 33.33% | 100.00% | 5.15 ms |
| Hybrid | 79.17% | 30.00% | 100.00% | 6.76 ms |
| Hybrid with reranking | 91.67% | 82.64% | 91.67% | 578.14 ms |

Hybrid reranking improved measured recall and candidate precision at a substantial local latency cost. Its only recall/support-label failure was `identity-theme`, which returned no evidence in this benchmark. The later live agent could judge Chapter 5 evidence sufficient, so this benchmark and the agent suites measure different stages. The direct strategy here is also distinct from the “Direct Librarian” live suite.

## Numbered attempts

Detailed pass counts and exact folder names are linked from [measurements](measurements.md). The intervention ledger below preserves the distinction between code changes, grading changes, and execution failures.

| Attempt | Change before the run | What the run established | Primary change evidence |
| --- | --- | --- | --- |
| 1 | Application-owned scope, broader private candidates, typed boundary alternatives, bounded review repair | Full selection; 17/29 native. Correct retrieval still met malformed inventory and overly strict source-audit failures. | [Integration design][integration] |
| 2 | Replace duplicate source inventory with unmapped-claim scan; nested boundary repair; exact connection IDs | Targeted subset; 11/17 native. Hume and smoke passed; combined-source support and invented quote mismatch issues remained. | [Decision ledger][decisions] |
| 3 | Distinct uncertain output shape; concurrent validation feedback; deterministic quote equality; combined support | Full selection; 21/29 native. Douglass and smoke passed; copied IDs, revisions, and no-preview behavior remained unreliable. | [Decision ledger][decisions] |
| 4 | Numeric canonical source indices; simpler whole-response repairs | Targeted subset; 8/10 native. Keller and Hume passed. Semantic review still found speculation and future-event implications. | [Post-attempt-3 design][repair3] |
| 5 | Clarify ordinary reflection and bounded no-evidence statements; explicit no-later-search rule | Full selection; 22/29 native. Wrong-record proof and missing reply declarations remained. | [Decision ledger][decisions] |
| 6 | Bind private excerpts to exact records; inspect uncovered reply spans and combined-claim membership | Full selection; 21/29 native. Mapping added, but Decimal serialization prevented a usable mapping result. | [Post-attempt-5 design][repair5] |
| 7 | Normalize whitespace for private proof matching; repair diagnostic serialization; clarify reflection instructions | Full selection; 22/29 native. Mapping 2/4: both negative controls were wrongly approved. Whitespace tolerance did not permit public quotation substitutions. | [Post-attempt-6 design][repair6] |
| 8 | Per-source and collective audits, literal support excerpts, quotation inventory, preservation of accepted declarations | Full selection; 20/29 native, mapping 4/4. New checks caught defects, but revision and semantic failures remained. | [Post-attempt-7 design][repair7] |
| 9 | Combined inventory/memory-ID repair; quote-index guidance; high reasoning | Targeted subset; 7/13 native, mapping 3/4. No established reasoning-effort benefit; provider failures were incompletely diagnosed. | [Post-attempt-8 design][repair8] |
| 10 | Restore requested nonclinical reflection; contribution-before-verdict output; provider status capture; continue high reasoning | Targeted subset; 5/9 native, mapping 3/4. Several reviews failed before valid output. Prompt and provider differences prevent a causal effort comparison. | [Post-attempt-9 design][repair9] |
| 11 | Return to medium reasoning; classify provider errors | Targeted subset; 3/6 native, mapping 4/4, smoke passed. False refusals and real mapping failures remained. | [Post-attempt-10 design][repair10] |
| 12 | Preserve exact quotation obligations through edits; supply the actual reader message to release-suite Provenance | Full selection; 19/29 native, mapping 2/4. Fixing the test context did not resolve wrong-source approvals. | [Post-attempt-11 design][repair11] |
| 13 | Membership across overlapping declarations; precise quotation-edge and span-copy repair hints | Targeted subset; 13/18 native, mapping 4/4. Final mapping success included recovery from initial false approvals. | [Post-attempt-12 design][repair12] and [overlap design][overlap] |
| 14 | Apply approved optional spoiler evidence and qualified Alice identity interpretation | Full selection; 25/29 native; direct 12/12. Some improvement came from corrected expectations. Pigeon's ambiguous growth still received unsafe authority. | [Expectation review][expectations] |
| 15 | Independent current-event identification before grant; literal repair help; revision discipline; 12-suite concurrency | Interrupted. Only recovered Pigeon 3/3, direct 12/12, and mapping 3/4 are complete saved outcomes. Four release progress rows exist, but no complete release result. | [Boundary design][boundary15], [recovery][recovery15] |
| 16 | Repair contradictory support/findings; improve quote-copy feedback; record private support only after actual grant | Full selection; 24/29 native. Mapping 2/4 and narrow identity anchors remained problems. | [Repair 16 review][repair16] |
| 17 | Show full canonical source beside each declared member; concise private proof; second valid Chapter 5 identity anchor; preserve attribution | Full selection; 22/29 native, with 429 and semantic failures. Largest measured review input grew from 49,879 to 94,264 characters, 1.89×. | [Provenance input design][projection17] |
| 18 | Attribution-audit consistency; direct per-case transcripts; precise quotation-wrapper guidance; six concurrent suites | Strongest full batch: 26/29 native, every component suite passed. No observed 429; three native failures and semantic gaps remained. | [Repair 18 review][repair18], [saved review][review18] |
| 19 | Ignore duplicate IDs only within `other_evidence_ids`; continuity proof guidance; multiple quotations and evidence-limit statements | Full selection; 23/29 native; release 6/12. Both 429 and semantic errors occurred. | [Repair 19 review][repair19] |
| 20 | Clarify final stop versus earlier background; preserve speaker/actor/modality; approved optional Douglass pit excerpt; three concurrent suites | Full selection; 2/29 native, release 0/12. Quota errors dominated; no clean quality conclusion. | [Repair 20 review][repair20] |
| 21 | One extra authorized rerun; runtime and adopted inputs fixed from 20 | Full selection; 23/29 native, release 11/12, no observed 429. Remaining failures exposed defects beyond availability. | [Attempt 21 review][review21] |

## Approvals and unrun experiments

The [expectation review][expectations] records the accepted changes. Before attempt 14, four scenarios admitted 17 reviewed additional canonical records while preserving every mandatory anchor and the same chapter ceilings. The component identity case accepted a qualified Chapter 5 interpretation. Before 17, another Chapter 5 anchor became valid; this did not make arbitrary Chapter 5 passages sufficient. Before 20, Douglass admitted an optional exact pit quotation under the existing approval.

The following were not demonstrated fixes:

- The Luna-versus-Sol review comparison was prepared for 12 fixed inputs and 24 reviews but never run live. Its preparation is not evidence that Sol performs better. [Comparison plan][comparison]
- The Roses corrective-discovery allowlist change remained a proposal. Missing Farm puppy-recognition evidence was never waived. [Expectation review][expectations]
- A proposed word-boundary patch for a reader quotation such as `she` inside `finished` was rejected because it could reject legitimate fragments without solving attribution. [Decision ledger][decisions]
- Filtering away unused sources was deferred because it might hide undeclared support or contrary evidence. [Repair 10 design][repair10]
- Shorter private proof and lower concurrency were mitigations to investigate, not proven cures for content filtering or 429 errors. [Boundary design][boundary15], [attempt 21 review][review21]

The user selected attempt 18 after reviewing later runs. Its runtime and adopted inputs were restored against 222 saved hashes and committed as the historical checkpoint. Later changes from 19–21 must not be presented as part of that checkpoint. Subsequent integration with main was locally tested but was not a new attempt-18 live run. [Checkpoint record](../../iteration-18-checkpoint.md)

[decisions]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/decisions.tsv
[pilot]: ../../../synthetic-journal-evaluation/reports/five-book-replay-2026-09-17/evaluation-report.md
[investigation]: ../../../synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/investigation.md
[standalone]: ../../../synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/standalone/analysis.md
[probe]: ../../../reports/librarian-fixes-2026-09-17/retrieval-probe.json
[retrieval-design]: ../../../reports/librarian-fixes-2026-09-17/design-retrieval.md
[integration]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/design-integration.md
[repair3]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-3-design.md
[repair5]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-5-design.md
[repair6]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-6-design.md
[repair7]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-7-design.md
[repair8]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-8-design.md
[repair9]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-9-design.md
[repair10]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-10-design.md
[repair11]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-11-design.md
[repair12]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-12-design.md
[overlap]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-12-overlap-design.md
[expectations]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/expectation-review.md
[boundary15]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-15-boundary-design.md
[recovery15]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-15-2fea4d3d/recovery-review.md
[repair16]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-16-review.md
[projection17]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-17-provenance-design.md
[repair18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-18-review.md
[review18]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/review-summary.md
[repair19]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-19-review.md
[repair20]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-20-review.md
[review21]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-21-f155ea01/review-summary.md
[comparison]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/review-model-comparison-plan.json
