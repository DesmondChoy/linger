# Librarian iteration 18 checkpoint

This checkpoint captures the implementation and adopted evaluation inputs used by iteration 18. The user selected it for commit after reviewing iterations 19 through 21. It is the strongest recorded full batch, with known failures still open. A higher score on one stochastic batch does not establish that its implementation is uniformly better.

The live results below belong to the original checkpoint `b2f6ec5`. A later rebase integrates main through `5790e36`, including memory recall and review changes. Local integration tests validate that combined version; the saved iteration 18 live results are not a new evaluation of the rebased code.

## Overall branch changes

- Resolve registered books through their canonical literary chapters and sections. Keller and Douglass section identifiers no longer need to be treated as chapter numbers.
- Decompose book requests into focused retrieval needs. Search the original reader text as a fallback, retain uncertain needs and below-cutoff private candidates, and assess completeness against the original request.
- Rerank long query/passage pairs in token windows while preserving canonical evidence IDs, text and locations.
- Keep reading permission in application code. Muse supplies search intent, while validated chapter or exact-passage grants determine access.
- Validate spoiler inference against complete candidate inventories, earlier-reader evidence and a separate identification of the current stopping event. Invalid or unresolved results grant no access.
- Check exact quotations, source attribution, complete claim coverage, and individual and joint source support before releasing Muse answers. Bounded repairs retain supported content and preserve reader-reported information.
- Expand synthetic evaluation across five books, permit approved optional spoiler support and Alice Chapter 5 alternatives, and validate evidence returned through connection discovery. Update the notebook, live validators, diagnostics, documentation and regression tests.

## Recorded live results

All 12 suites ran once using `openai:gpt-5.6-luna` with medium reasoning and six concurrent workers. No HTTP 429 was observed in iteration 18.

| Evaluation | Result |
| --- | --- |
| Native scenario Scenes | 26/29 |
| Native judgments | 28/32 |
| Direct retrieval | 12/12 |
| Answer release | 12/12 |
| Claim mapping | 4/4 |
| Outside-essay smoke | Pass |

All 29 Scenes were reviewed, including passing outputs. Five specific-event inputs obtained correct independent chapter grants; six ambiguous controls clarified safely. The boundary audit found no unauthorized ceiling or evidence disclosure. The negative path of the independent event check was not exercised.

See the [saved iteration 18 review](../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/iteration-18-c15a6da6/review-summary.md) for the original results and detailed reviews. Statements there about withholding a commit describe the decision at that time; the user's subsequent instruction explicitly selects this checkpoint for commit.

## Open issues

1. **Douglass boundary inference:** the model first associates an excerpt with the wrong record, then fails inventory validation on a duplicate entry. Available evidence does not become an accepted boundary candidate.
2. **Farm continuity evidence:** the correct Chapter 5 grant omits the mandatory passage identifying the grown dogs as the earlier puppies. Provenance repair also encounters a content-filtered output in this batch.
3. **Roses review and expectations:** the reviewer can reject defensible evidence-limit statements, and the concealment comparison has an incomplete source mapping. The separate proposal to admit corrective discovery evidence in connection tests still needs adoption.
4. **Semantic coverage despite passing grades:** Pinocchio's explicit answer passes with an undeclared source-dependent interpretation. Exact quotation and structural checks do not establish that every interpretation is supported.
5. **Reviewer consistency:** valid nested quotations and literary interpretations can attract unnecessary objections. Passing component tests do not establish reliable review across all native scenarios.

Later runs additionally exposed incorrect speaker attribution, an unsupported workplace concession, and a conflict between complete compound-claim proof and an 800-character single-excerpt limit. Those are follow-up evidence from later versions, not iteration 18 outcomes. The excerpt guidance introduced after iteration 18 is not part of this checkpoint.

Beads keeps the broader work open under `linger-9oqp`, with semantic review follow-up `linger-9oqp.18`, proof-contract follow-up `linger-9oqp.20`, and expectation review `linger-42d3`. Selecting this checkpoint does not close those issues.

## Recovery and validation

Runtime and adopted inputs are recovered against iteration 18's 222-file SHA-256 manifest. Later versions are preserved locally under `tmp/iteration18-recovery/preserved-after21`, and the full run ledger remains intact. Later run results are historical evidence and are not relabeled as iteration 18 results. No new live evaluation was requested or performed for this commit.

The historical local checkpoint passed 1,896 tests and 670 subtests, followed by 95 focused tests and 10 subtests after a prompt clarification. Fresh verification of the restored checkpoint passed all 1,896 tests and 670 subtests. All 222 source hashes still match after testing. The checkpoint receipt and local validation log are saved alongside the evaluation. The initial expanded check also exercised an unused model-comparison experiment with stale fixtures; that experiment is excluded from this commit and tracked separately as `linger-9oqp.22`.
