# Combined Librarian evaluation investigation

All **11 listed live suites completed**, covering **54 Scenes/cases**, using `openai:gpt-5.6-luna`. The missing external-essay smoke and two remaining cross-source scenarios ran once; the completed book-only runs were reused. This report supersedes the earlier eight-suite, book-only status. Four historical scenarios remain preflight-incompatible or lack adoption; their ten Scenes were not run.

The failures are not one reranker problem. Focused retrieval recovers the five specific stopping events, but candidate selection still loses a relevant alternative in Keller. Independently, the boundary judge grants permission for ambiguous events, Muse can narrow an already correct boundary, and cross-source replies expose source-mapping and review-output defects. Some recorded failures are grading mismatches, and one passing spoiler grade hides a missing quotation.

## The three requested paths

| Path | Completed evidence | Conclusion |
| --- | --- | --- |
| `evals/librarian/live_validation.py` | All 12 release cases; aggregate targets passed | 91.67% evidence recall, 100% citation precision, 91.67% strength accuracy. Explicitly confirmed chapters mean this does not validate ambiguous boundary inference. |
| `notebooks/librarian_manual_evaluation.ipynb` | Its real evaluation helper and scorer executed for all 12 cases | 95.83% recall, 100% precision, 91.67% strength accuracy. One citation-format comparison failure and one disputed strength label remain. This was helper execution, not a cell-by-cell Jupyter/UI run. |
| `evals/serendipity/objective_cases/cross-source-outside-essay-v1.json` | One production replay, all six structural stages passed | Actual Exa search and two page fetches; Alice Chapter 5 grounding; Plato/Gordon candidate comparison; Provenance revision followed by release. Independent semantic-review approval remains separate. |

The smoke produced a useful, qualified comparison with Plato's *Meno*. Its automatic schema repairs and claim revision demonstrate recovery within the run; they were not manually repeated evaluations. [Three-path investigation](standalone/investigation.md) · [Smoke output](standalone/cross-source-outside-essay-approved.json) · [Smoke Logfire evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/cross_source_tentative_connection/compare?experiment=01a0afdc9b96c7e22e4ecbe5f2c50556-03ce3ac3474855bc).

## Combined scenario results

Recorded scenario grades are **17/29 Scenes** and **19/32 judgments passed**. These are single-run results, not a reliability estimate. The two 12-case component suites and one smoke case complete the 54-case coverage; do not combine their different metrics into a single pass rate.

| Scenario | Scenes passed | Main interpretation |
| --- | ---: | --- |
| Alice event-led | 3/4 | Correct Chapter 3; extra valid support triggers strict matching failure. Ambiguity clarifies safely. |
| Douglass | 2/4 | Correct Chapter 7; ambiguous return wrongly grants Chapter 8 despite both alternatives being retrieved. |
| Helen Keller | 3/4 | Correct Chapter 10 becomes a Chapter 9 search; the spoiler-only pass misses quotation failure. Ambiguous pet loss grants Chapter 10; canary alternative was dropped before judgment. |
| Animal Farm | 2/4 | Correct Chapter 5 with extra valid support. Invalid uncertainty output safely falls back to clarification. |
| Pinocchio | 2/4 | Correct Chapter 9 with a support-set mismatch. Ambiguous school detour wrongly grants Chapter 26 despite both alternatives being retrieved. |
| Alice Pigeon | 1/3 | Correct Chapter 5 becomes a Chapter 4 search. Separate ambiguous growth wrongly grants scope, but final fallback prevents story disclosure. |
| Roses / error reporting | 1/3 | Missing memory declaration and cross-record claim mapping; another Scene loses a useful restraint reply after an invalid Provenance critique. Personal control passes. |
| Identity / Hume | 3/3 | Tentative connection, useful restraint, and personal control all pass; observed replies support those results. |

Every Scene has a completed individual review, linked through the [full run manifest](investigation-results.json). The last two scenarios use frozen public pages; their observed `get_page` calls stayed within those pages, with no `web_search` event. The external-essay smoke separately exercised live Exa retrieval. None of these passes establishes safe ambiguous progress inference.

## Confirmed causes and correction order

**1. Stop ambiguous matches becoming spoiler authority.** Douglass and Pinocchio already have both competing occurrences in the private pool. The judge selects one with 0.97/0.98 confidence, and its output passes structural checks. Keller similarly grants Chapter 10 at 0.99 despite the reader having forgotten which animal and surroundings. Current checks prove source identities, chapter consistency, and declared support; they do not establish that the reader's words distinguish the event. Provenance then receives the bad ceiling as trusted application context and can approve a factually supported but unauthorized answer. Three saved replies disclose material that should have waited for clarification.

The correction belongs at boundary authorization. Preserve broad private retrieval, but require reader-supplied distinguishing support and handle unresolved competing occurrences explicitly. Repeating the same vague description in memory is not independent confirmation. Raising confidence thresholds or treating relevance as permission does not solve this. Typed proof improves auditability but still requires semantic checking. Trackers: `linger-14sc`, `linger-69gn`, `linger-rt2x`.

**2. Preserve the application-owned inclusive scope through the search call.** Keller and Pigeon correctly infer Chapters 10 and 5, but Muse passes them to search as `started`. The existing, deliberate conversion subtracts one, producing 9 and 4. The requested passage is then excluded before retrieval. Let the adapter use the validated application scope without requiring Muse to re-encode chapter completion, while preserving genuine reader-started semantics and any explicit narrowing contract. Tracker: `linger-hn7j`.

**3. Repair the remaining private candidate recall loss.** A cached offline probe reproduced Keller's exact eight-record private pool. The missing canary passage reaches rank 4 in the memory-query fusion list, then falls to reranker rank 12/15, score 0.000558799, and is excluded by the five-record selection. The private path protects only the single fusion leader and fills the remaining slots from reranked candidates. This was not decomposition omitting the need, a 0.5 reranker cutoff, or exhaustion of the combined pool budget. Preserve alternative strong retrieval signals through private judgment and validate candidate diversity with this exact canary/crab case. The reranker's known token limit remains an additional issue; this probe did not establish whether truncation caused this particular canary score. Trackers: `linger-69gn`, `linger-n8vx`.

These three causes, local reproductions, exact source lines and verification targets are in the [scenario root-cause report](investigation-scenarios.md), [Keller search probe](keller-recall-probe.log), and [reranker scores](keller-rerank-probe.json).

**4. Make source mappings and review revisions dependable.** Roses S1 uses the stored fact that the reader corrected a billing error and stayed silent, but declares no memory evidence. It also maps “The concealment fails” to the earlier intention-only book passage, although the later discovery passage is separately available. Provenance misses both mapping problems. These are supported failures even though the book statement itself is true and within the confirmed Chapter 8.

Roses S2 retrieves the sources and drafts a useful bounded refusal. After revision, Provenance claims that a mapped memory sentence still contains an adjacent interpretation. Its quoted finding does not occur at the current declared path. Replaying the saved input through the validator reproduces the rejection; the application correctly blocks that invalid review and emits a generic fallback. Preserve the validator and add bounded, input-aware correction of malformed review findings. Hume's valid revise→pass and the smoke's successful revision show that this path can work. Trackers: `linger-s82k`, `linger-55r9`, `linger-ebwq`. [Cross-source investigation](investigation-cross-source.md).

**5. Make uncertainty easier to express without weakening the safe fallback.** Farm's model attempts an uncertain decision, first with a forbidden field, then with grant fields that uncertainty forbids. Both fail validation. The application asks a safe clarification and releases no book evidence. Represent uncertainty with a distinct output shape, and retain the fallback. This is a real output-contract failure, not an observed spoiler leak. Tracker: `linger-bdtp`.

**6. Correct the evaluation contracts separately.** Closed-set support matching rejects extra valid evidence in Alice, Douglass and Farm. Keller's spoiler-only checks do not require its requested quotation. A notebook citation check rejects one normalized blank line despite canonical resolution. `identity-theme` asks a question directly supported by the selected Chapter 5 passage, while its frozen gold expects weak support and two episodes. Roses' extra Chapter 8 discovery evidence validly corrects the reader's assertion that the Queen never finds out, but falls outside the exact adopted allowlist. Review these intentions and checks without silently changing grades or broadening permitted evidence indiscriminately. The missing memory mapping remains a real Roses failure regardless of the allowlist issue. Tracker: `linger-42d3`. [Grading investigation and code references](investigation-grading.md).

## Decomposition and the false-negative concern

The current planner is not the only route into retrieval. Focused parts, the original reader request, and earlier reader statements are searched; uncertain needs remain eligible. Candidate streams are interleaved. The assessor can recover omitted needs from the original request and must report missing support instead of claiming sufficiency. The existing recall and boundary-planning tests passed again: **16 tests**.

That protection is incomplete: candidates can still drop during ranking, and newly noticed needs during assessment do not cause another retrieval pass. The observed Keller loss proves that retaining the query alone is insufficient. Keep recall broad inside the private, scoped process, then separately enforce what evidence supports an answer and what reader evidence authorizes disclosure. The former can tolerate extra candidates; the latter must not grant a guessed stopping point.

## Evidence, limits, and handoff

No production code or adopted expectation was changed during this investigation. The earlier runner/notebook compatibility repairs remain as previously reported. New files are reports, local probes, the observational smoke adapter, and run artifacts; Beads records contain the follow-ups. No commits or pushes were made.

Verification covered exact saved-output validation, the matching-function probe, cached hybrid reproduction of Keller's pool, 16 existing focused tests, and `git diff --check`. All **36 authority files across 12 scenarios** still match preflight hashes. The smoke case hash also remained unchanged. Earlier runs are reused, not treated as new repeated measurements. [Verification receipt](investigation-verification.json) · [Run manifest and individual reports](investigation-results.json).

The four blocked historical scenarios still account for ten unexercised Scenes: three scenarios are incompatible with the current schema or typed expectation contract, and one lacks independent adoption. Their complete preflight reviews are in [preflight.json](preflight.json). None was silently migrated. Remote Logfire visibility was not read back; the emitted links and successful flushes are preserved. The component release artifact omits reply text, so its Pigeon coverage loss cannot be fully assessed locally. Its old usage accounting is unavailable rather than zero (`linger-c0kp`).
