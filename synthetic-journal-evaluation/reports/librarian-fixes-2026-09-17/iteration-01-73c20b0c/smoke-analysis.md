# Outside-essay smoke analysis

The smoke completed but failed review: four stages passed, Provenance review
failed, and deterministic release was not reached. The reader received the
application error response. This is a review-output failure, not a search outage.

| Stage | Recorded result | Saved behavior and interpretation |
| --- | --- | --- |
| Invocation | Passed | The reader explicitly finished Alice chapter 5 and requested an outside philosophical source; connection discovery ran. |
| Retrieval | Passed | Exa searches and page retrieval succeeded, and scoped book retrieval supplied the Caterpillar passage. No private memory was involved. |
| Serendipity selection | Passed | Discovery selected a proposal using the chapter and the Stanford Encyclopedia of Philosophy’s Socrates entry. The frozen canonical review bundle contains these two sources. |
| Muse presentation | Passed | The draft visibly cited the essay and chapter, quoted the book, and offered a tentative comparison. This hard pass does not establish complete claim mapping: two comparisons were assigned to the web record without clearly separating the book contribution. |
| Provenance review | Failed | Initial review validly requested repair of the source mappings. Muse revised once. The second review exhausted three output attempts: an over-300-character finding quote, then an audit span missing the reply’s Markdown, then an alleged undeclared source use. |
| Deterministic release | Not reached | No accepted second review existed. Only the first `revise` verdict was recorded, so the application withheld the candidate. |

The final review error was reproduced offline against its exact saved input.
Its source audit included the exact book quotation, already bound by the
declaration’s `exact_quote`, but the duplicate inventory check demanded that it
also occur in `supported_claims`. Other audit spans added terminal periods absent
from otherwise complete declared clauses. These are structural false alarms,
not evidence of an invented quotation. The final critique also asked for a
book mapping of a contrast whose Caterpillar clause was already mapped to the
book. That is an additional overstrict reading of joint-source contribution.

There remains a substantive repair question: the revised “both use composed
questioning” comparison was again assigned only to the web record, and the
final sentence interpreting the book scene had no explicit mapping. The safe
correction must preserve independent detection of missing source contributions
while permitting separately mapped contributions, exact quotations, and ordinary
reflective questions. Merely accepting the last review as a pass would not fix
those issues.

Replace the duplicate source-use inventory with the approved independent
`unmapped_claims` audit; retain complete named-source support judgments and
findings for admitted defects. Aggregate precise current-input repair errors
within the existing retry budget. Verify offline that a bound exact quotation,
split claim mappings and citation formatting do not trigger duplicate-coverage
failures, while a genuinely unsupported or unmapped contribution still does.
No live calls, runtime edits, or expectation changes were made for this analysis.

Evidence: [smoke result](suite-smoke.json), [full diagnostics](suite-smoke.diagnostics.json),
[run log](suite-smoke.log). The diagnostic export reports telemetry flushed;
remote visibility was not checked.
