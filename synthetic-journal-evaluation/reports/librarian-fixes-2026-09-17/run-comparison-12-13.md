# Why iterations 12 and 13 differ

The result changed because the application changed and the model produced different answers and reviews. Iteration 13 also ran a smaller selection, so its headline scene count cannot be compared directly with iteration 12's full-set count. Both used `openai:gpt-5.6-luna` with medium reasoning. Each batch's source manifest remained unchanged throughout execution; the source changed between batches.

| Same scenario selection | Iteration 12 | Iteration 13 |
| --- | ---: | ---: |
| Roses | 1/3 | 2/3 |
| Animal Farm | 3/4 | 3/4 |
| Hume | 2/3 | 2/3 |
| Alice event-led | 2/4 | 2/4 |
| Helen Keller | 3/4 | 4/4 |
| Comparable scene total | 11/18 | 13/18 |
| Release component cases | 10/12 | 10/12 |
| Fixed mapping controls | 2/4 | 4/4 |
| Outside-essay smoke | Failed | Failed |

The full iteration 12 scene result was 19/29. Iteration 13 omitted eleven of those scenes and the direct notebook suite. It cannot establish a full-set pass.

Three application changes preceded iteration 13: claim grouping now accounts for actual overlap between declared response spans; Muse receives more precise quote-edge and outer-whitespace repair feedback; failed mapping runs retain sanitized attempt diagnostics. The changes passed 1,795 local tests and 648 subtests. These local checks establish mechanical behavior, not universal correctness of model judgments.

The saved failures show why an unchanged score can hide a different problem. In iteration 12, the outside-essay review incorrectly saw a missing source because the computed claim table omitted an existing overlapping declaration. In iteration 13, the model actually omitted the second source from its revised hybrid claim. There was no declaration for the corrected overlap calculation to discover. The first is a fixed application defect; the second remains a model repair failure. Iteration 12 also had a separately reviewable concluding inference and other declaration defects; correcting the overlap does not automatically validate that entire reply.

The mapping control inputs retain the same authoritative content across the two runs. Their computed support tables changed. Iteration 13's two negative controls initially received false approvals, but validation feedback led to correct final rejections. Therefore 4/4 means four correct final outcomes after bounded repairs, not four correct first judgments or proof that semantic review is reliable.

Animal Farm's 3/4 also needs context. Its explicit reflection is now supported by its declared passages, correcting iteration 12's misleading pass. Its inferred boundary fails because both model responses were content-filtered and truncated before an accepted structured output. That is different from the earlier extra-proof mismatch.

Some failures concern expected answers rather than the retrieval or response itself. Alice's inferred ceiling remains Chapter 3 with the required anchors and extra relevant, verified in-scope passages. The strict adopted matcher rejects the additional passages. That expectation has not been changed or counted as a pass.

A controlled next experiment should reuse identical saved inputs and change only the reviewer model. It can test reviewer consistency without allowing fresh retrieval or new prose to confound the comparison. It cannot establish Muse repair reliability or replace a final full-set evaluation. The additional model has not been executed or selected as a production default.

Evidence: [iteration 12 summary](iteration-12-7098e696/summary.json), [iteration 13 summary](iteration-13-4d9bca6b/summary.json), [iteration 13 mapping review](iteration-13-4d9bca6b/mapping-analysis.md), [iteration 13 smoke review](iteration-13-4d9bca6b/smoke13-analysis.md), [repair design](repair-12-design.md), [overlap design](repair-12-overlap-design.md), [local checks](local-tests-repair-12.log). No strict grades, adopted inputs, or model outputs were rewritten for this comparison.
