# Iteration 14: mapping controls

Final **4/4** is credible after the existing bounded repairs. Both negative controls initially receive false approvals; source-local excerpt validation prevents those approvals from being accepted. Their next attempts correctly reject the missing support. Both positive controls pass on their first attempt.

Read `suite-mapping.json`: all four exact review inputs, output attempts, retry feedback, final reviews, and grades. Every full input equals its iteration13 counterpart, including derived projections. No control or expected answer changed. Independent offline validation accepts all four final reviews against those saved inputs.

| Control | Requests | Independent assessment |
| --- | ---: | --- |
| Wrong record | 2 | First pass joins memory and verse quotations under the earlier identity record, where neither occurs. Source-local validation rejects that excerpt. Second revise correctly distinguishes the available later record from the incorrectly declared earlier one and requests remapping or removal. |
| Correct record | 1 | Pass uses an authentic continuous excerpt containing the memory complaint, Caterpillar's intervening question, and verse report. The declared record supports both clauses. |
| Missing joint contribution | 2 | First pass duplicates the same group member and borrows the later memory/verse passage under the earlier record. Feedback identifies both defects. Second retains the genuine identity/size contribution but marks the complete claim unsupported because its later verse clause lacks its source. Credible final rejection. |
| Complete joint contribution | 1 | Pass binds authentic excerpts to both distinct records and assesses their combined support. The later excerpt itself highlights the memory complaint, but the full named later record also contains the verse report. Credible joint approval. |

The two relevant records remain `pg11-v01b38ea4-ch05-ln0960-1016` and `pg11-v01b38ea4-ch05-ln1004-1056`. A passage elsewhere in the supplied bundle cannot silently satisfy a claim declared only against the first. Final reviews respect that distinction here; initial model attempts do not.

All four diagnostic statuses are success, with complete recorded usage and null provider failure fields. Request counts2/1/2/1 reflect model output repair, not added evaluation runs. This result demonstrates the usefulness of exact source binding in these controls; it does not establish that authentic excerpts always imply a correct support summary. No provider calls, historical rewrites, source edits, or expectation changes were made during this review.
