The retrieval benchmark and both approved 12-case book suites completed. The full release suite met its aggregate targets. The direct Librarian suite retained one strength-label mismatch and one strict source-format comparison failure. No failed live case was rerun, and no expectations were changed. The cross-source smoke has not run: it remains held for separate explicit Exa/search-query authorization.

| Suite | Coverage | Recall | Precision | Strength accuracy | Outcome |
| --- | --- | ---: | ---: | ---: | --- |
| Retrieval benchmark, selected hybrid reranking | 12 cases × 5 strategies × 3 repetitions = 180 searches | 91.67% | 82.64% | 91.67% | Retrieval-only precision target missed; scope/citation gates passed |
| Direct Librarian, actual notebook helpers | 12/12 result responses | 95.83% | 100% | 91.67% | All spoiler-safe; strict citation-text check failed in one case |
| Librarian → Muse → Provenance → release | 12/12 Muse candidates released | 91.67% | 100% | 91.67% | `targets_pass=true`; answerable release rate 100%; no spoiler exposure; citation-resolution checks passed |

The direct and release runs each used process-local `openai:gpt-5.6-luna`, cached local retrieval models, and disabled web search. Existing telemetry support instrumented the runs; both reported successful flushes. Direct trace: `01a0af9bc268a9a80fcd936890482971`. Release trace: `01a0af9bc26c9a383c67ddbd2051bf87`. No dashboard URL was invented.

| Case | Expected strength | Direct strength / recall | Release strength / recall | Observations |
| --- | --- | --- | --- | --- |
| rabbit-watch | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| drink-me | sufficient | sufficient / 100% | sufficient / 100% | Direct strict source-text check differs by one internal blank line; release citation checks passed |
| pool-of-tears | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| caucus-prizes | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| giant-puppy | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| identity-change | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| father-william | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| pigeon-serpent | sufficient | sufficient / 100% | sufficient / 50% | Provenance requested revision for `unsupported_claim`, then passed; final citation covers one of two gold ranges |
| identity-theme | weak | sufficient / 50% | sufficient / 50% | Same fixed-label mismatch and partial gold coverage in both runs; interpretation discussed below |
| exact-caucus-quote | sufficient | sufficient / 100% | sufficient / 100% | No recorded discrepancy |
| future-cheshire | none | none / 100% | none / 100% | No later-chapter evidence exposed |
| absent-spaceship | none | none / 100% | none / 100% | No nonexistent scene evidence returned |

`identity-theme` asks, “How do Alice's changing size and uncertain identity reinforce each other?” It does not require a whole-book synthesis or comparison of multiple named episodes. Its frozen gold labels the answer `weak` and requires both Chapter 4 lines 762–770 and Chapter 5 lines 966–981; the case contains no rationale and no narrower `required_ranges` override. Both live runs selected Chapter 5 lines 960–1016. That passage explicitly joins Alice's uncertainty about who she is with the confusion of changing size. The current evidence-assessment skill asks for the shortest useful supported answer and says an additional illustration is not itself a requirement. This is therefore a plausible stale coverage/strength expectation, rather than confirmed unsupported model confidence. The 50% recall and incorrect-strength grades remain unchanged. Resolving the semantic disagreement requires human review of the gold intent; no additional model review was invoked.

For `pigeon-serpent`, the direct run selected Chapter 5 lines 1179–1219, which overlaps both gold ranges. The release run ultimately cited lines 1208–1237, overlapping only the second. Its recorded Provenance sequence was `revise`, then `pass`, with `unsupported_claim` recorded before the final release. The metadata-only release report does not retain the original or revised reply, so it cannot establish whether every requested explanatory detail survived revision. Aggregate target passage does not erase this measured coverage loss.

The direct suite's aggregate `all_citations_resolve=false` comes from **one case, `drink-me`**, not all individual citations. Its ID `pg11-v01b38ea4-ch01-ln0186-0219` resolves through the canonical resolver and reproduces the returned text. Comparing against the immutable source range finds 1,602 versus 1,603 characters: one internal blank line between the decorative stars and the following paragraph is collapsed. `apps/backend/librarian.py::_record_from_paragraphs` joins paragraphs with two newlines; the notebook's benchmark scorer instead requires exact original-source string equality. This is a grader/canonical-normalization mismatch, not evidence of an invented citation. The failing original grade is preserved in the JSON, and the offline diff is saved in `direct-citation-diagnostic.json`.

The retrieval benchmark used all five configurations:

| Strategy | Recall | Candidate precision | Strength accuracy | Warm p95 latency |
| --- | ---: | ---: | ---: | ---: |
| direct | 50.00% | 16.25% | 66.67% | 6.53 ms |
| bm25 | 75.00% | 28.33% | 91.67% | 5.51 ms |
| semantic | 79.17% | 33.33% | 100.00% | 5.15 ms |
| hybrid | 79.17% | 30.00% | 100.00% | 6.76 ms |
| hybrid_reranked | 91.67% | 82.64% | 91.67% | 578.14 ms |

All five passed benchmark spoiler-scope and citation-resolution gates. Selected hybrid reranking returned no evidence for `identity-theme`, its only recall/strength failure. Its candidate precision was below 100% for `rabbit-watch` (50%), `drink-me` (66.67%), `pool-of-tears` (50%), and `father-william` (25%). The benchmark's own retrieval implementations do not exercise production request planning or evidence selection. Its three repetitions measure latency, not repeated model reliability. It began before the subsequent offline-environment instruction, completed with available local models, and was not repeated.

The preserved initial `live-validation.log` records a local pre-provider failure on `rabbit-watch`: `application did not confirm reading context`. Zero cases or provider calls completed in that attempt. An offline probe showed that the original introduction was parsed as the title “Alice's Adventures in Wonderland, and I've completed” for all 12 cases. The actual production parser bug remains separately tracked as `linger-fasa`. The approved harness workaround puts the completed chapter before the title, preserving every original question and ceiling. The release harness now binds and resets `reader_message`; notebook helpers do the same and no longer pass the removed `query` tool argument. Fifteen new offline compatibility checks failed before those fixes; afterward, those checks and two existing evidence-filtering checks passed. Notebook outputs, metadata, and unrelated cells were preserved; two explanatory markdown cells now describe planning and assessment calls accurately.

Reporting limits remain. The release suite's usage fields are unavailable, not zero: installed PydanticAI exposes `AgentRunResult.usage` as a property, but `_usage` calls it as a method and catches the resulting error. Even corrected, that helper currently counts only Muse and Provenance, excluding Librarian planning/assessment. This instrumentation defect was left unchanged after the run and did not affect grading. Release p95 latency was 67.22 seconds and mean latency 34.21 seconds. The two suites use different citation checks, so the release citation pass does not contradict the stricter notebook whitespace failure. These are one-pass outcomes on frozen Alice questions, not five-book boundary-inference coverage or independent semantic approval.

Artifacts: `benchmark.json` and `.log`; the preserved initial `live-validation.log`; `harness-probe.json`; `live-release-approved.json`, `.progress.json`, and `.log`; `notebook-direct-approved.json`, `.progress.json`, and `.log`; `direct-citation-diagnostic.json`; and the reproducible one-shot adapter `run_live.py`. Existing checked-in reports and case expectations were preserved. No production code, tracker, or commit was changed in this lane.
