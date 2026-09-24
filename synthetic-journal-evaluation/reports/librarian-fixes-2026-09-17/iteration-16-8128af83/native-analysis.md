# Iteration 16: native scenario review

The eight native suites completed with **24/29 Scenes and 26/32 judgments passing**, no ungraded Scenes. Every Scene has a completed semantic review, including every pass. All eight native analyses were rendered and read. The report index contains **95** reports: 86 through iteration 14, one recovered iteration-15 Pigeon report, and these eight.

| Suite | Scenes | Judgments | Interpretation |
| --- | --- | --- | --- |
| Pigeon (4) | 3/3 | 4/4 | Exact quote and useful personal reflection pass; ambiguous growth safely clarifies. |
| Roses (6) | 1/3 | 1/4 | Two sourced replies fail only on the extra valid Chapter 8 citation used to correct the reader’s false premise. |
| Animal Farm (7) | 3/4 | 3/4 | Specific inference blocked by two content-filtered provider outputs; explicit quotation and joint source interpretation pass. |
| Hume (8) | 2/3 | 3/4 | Positive connection declines after revision adds quoted “myself”; authenticity restraint and personal wording pass. |
| Douglass (9) | 4/4 | 4/4 | Exact quote, correct Chapter 7 inference, useful personal reflection, safe ambiguity response. |
| Alice race (10) | 3/4 | 3/4 | Explicit reflection declines on a disputed recipient-summary mapping; inferred reflection succeeds with both records mapped. |
| Keller (11) | 4/4 | 4/4 | Original his/he quotation preserved; corpus sec012 correctly means literary Part I Chapter 10. |
| Pinocchio (12) | 4/4 | 4/4 | Required quotation and Chapter 9 inference pass; explicit reflection omits part of the broader authored comparison. |

The review assessments are **17 credible passes, 7 passes with limitations, 3 potential false negatives, and 2 supported failures**. These labels do not overwrite mechanical grades. The seven limitations comprise six broad but safe clarification questions and Pinocchio’s narrower-than-authored narrative coverage. No definite misleading native pass was found in the source/quotation review; separate direct, release, mapping and smoke reviews have their own scope and findings.

## Failures and next useful changes

**Animal Farm inference:** both private boundary model responses end `content_filter`, truncating source-proof text beginning with the Jessie/Bluebell puppies passage. The exchange has no valid output; the application safely clarifies before independent event identification or response retrieval. The five mismatch details share this upstream cause. They do not demonstrate an ambiguous input or an invalid Ground truth. Brief canonical anchors can reduce unnecessary copied text while preserving exact occurrence validation; the next batch must establish that a complete typed output actually results.

**Roses S1 and S2:** the current Line incorrectly says the Queen never discovers the planting mistake. The replies correctly consult `pg11-v01b38ea4-ch08-ln2018-2074`, which contains her inspection and execution order, and declare it alongside the original gardener passage. That record is within the completed chapter but absent from the unchanged connection citation allowlist. The only recorded failure is `unpermitted_citation`. Final revisions correctly remove an unsupported honesty contrast and leave the reader’s personal cause unresolved. S1 paraphrases the chapter although authored prose asks for a quotation; that broader coverage gap is separate from its citation failure. The previous human approval amended spoiler support, not this connection allowlist; no adoption or expectation was silently changed.

**Hume S1:** the first review correctly identifies unbound source fragments and an unmapped continuity statement. Revision repairs these and supplies coherent three-source accounts, but introduces quoted “myself” in its Alice interpretation. The final review treats that occurrence as another source quotation without an exact binding, so the one-revision release path declines. The word could be metalinguistic framing rather than direct quotation; plain prose would remove the avoidable ambiguity. This is not insufficient retrieval or an erroneous Hume record.

**Alice explicit:** the first accepted summary says “the announcement makes everyone both a winner and a recipient.” The revision changes it to “So everyone is made both a winner and a recipient,” dropping the announcement attribution. The final reviewer reads this as completed receipt, requiring the thimble record as well. The declared first record already states everybody wins, all must have prizes, Alice distributes comfits, and the Mouse insists that Alice must also have a prize. A designated-recipient interpretation is therefore supported; actual delivery to Alice is established in the later record, already available and mapped elsewhere. This is a potential false negative with a real unmet request. The smallest robust drafting change is to preserve unaffected accepted source claims and their attribution, or map both records when rewriting them into a broader event claim. Automatically attaching every available record or bypassing review would not be justified.

## Passing behavior and limits

Pigeon, Keller and Douglass reproduce their full requested quotations. Keller retains the source’s original `his` and `he`; both Keller and Douglass present literary chapter numbers rather than treating physical section IDs as chapter numbers. Farm’s explicit reply declares its leadership-rhetoric and silenced-dissent records jointly, and each record’s audit excerpt resolves to that record. Hume’s restraint reply accurately separates the fictional passage, philosophical account and one-day personal note, without declaring either voice false or guaranteeing both authentic.

Alice’s inferred reply preserves the full Dodo announcement, maps the prize sequence to both records, and frames the reader analogy as a lens to test. Its current stop does not extend into Chapter 4. Pinocchio’s inferred reply preserves the complete school-tomorrow quote and stops at Chapter 9 without the ending. Its explicit reflection is useful and non-shaming, but does not actually discuss the promised coat or the narrator’s reminder of Geppetto’s sacrifice. Those contextual records are permitted rather than mechanically required, so that pass is narrower than the full authored prose.

All personal-only controls produce useful wording or practical reflection without book retrieval, absent-Prop use, clinical claims or invented concrete biography. All six ambiguous-boundary controls return safe, content-free clarification without releasing candidate events. Their generic latest-chapter-or-scene question is less helpful than inviting a remembered participant or setting, especially when the reader explicitly cannot locate the scene.

All successful distinctive inferences exercise the independent event identifier. Every ambiguous negative is already stopped by primary boundary inference, and Farm’s specific inference fails before the gate. Consequently this batch does **not** exercise the new gate’s rejection path or the evaluator correction for a denied candidate. The latter remains covered by the local regression, not a new live observation. Independent boundary review is recorded separately in `boundary-analysis.md` when available.

## Audit trail

Each native report uses the helper’s emitted analysis path. Its current backstory, Ground truth and adoption hashes matched its run-start receipt before review. Only the analysis `review` field was completed; original artifacts, grades and authority files were left intact. The deterministic renderer validated all reports and their full Scene coverage. [The report index](../report-index.json) contains the exact artifact, JSON and Markdown paths.

All eight native telemetry receipts report a successful flush and supply emitted Logfire links. Remote visibility remains **unverified**: no remote read-back was performed. A flush is not proof of visibility. No provider call, extra live iteration, source edit or Ground truth amendment was performed for this review.
