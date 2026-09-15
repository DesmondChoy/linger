# Live regression rounds on 15 September 2026

This allowance covered ten scenario replays using `openai:gpt-5.6-luna` across eight implementation versions. Each replay had three Scenes and four judgments. The approved Backstory, Ground truth, and adoption bytes stayed unchanged.

These results predate the cleanup and rebase onto main. Main and Roses passed earlier versions. Only Pigeon passed the last live-tested implementation. No live calls were made during cleanup.

| Round | Scenario | Attempt | Passed Scenes | Passed judgments | Observation | Report |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Main | Plan book requirements before selection. | 1/3 | 1/4 | Extra invented requirement selected unnecessary evidence; wrong-passage Provenance approval also observed. | [Analysis](../packages/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T105240+0800-e99874a6.md) |
| 2 | Main | Use exact reader fragments instead of rewritten questions. | 3/3 | 4/4 | Correct selection on both paths; visible chapter reference still missing. | [Analysis](../packages/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T110103+0800-c19fee8b.md) |
| 3 | Roses | Test round 2 implementation on Roses. | 1/3 | 1/4 | Quotation repairs exhausted; unnecessary outcome passage selected. | [Analysis](../scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T110510+0800-60e14983.md) |
| 4 | Roses | Separate scene references from factual questions; aggregate repair feedback. | 1/3 | 1/4 | Required passage missed; citation formatting still failed. | [Analysis](../scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T111907+0800-3587b1d3.md) |
| 5 | Roses | Plan before retrieval; share exact search wording and citation repair hints. | 1/3 | 1/4 | Capitalization mismatch rejected the plan; quotation line breaks exhausted repairs. | [Analysis](../scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T113717+0800-41c1e191.md) |
| 6 | Roses | Repair exact-span errors within existing retries; supply canonical quote hints. | 3/3 | 4/4 | All checks passed; review removed unsupported personal interpretation. | [Analysis](../scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-15T115855+0800-37611212.md) |
| 7 | Pigeon | Test round 6 implementation on Pigeon. | 2/3 | 2/4 | Supported memory ignored; clarification blocked quotation. Optional wording invented tenure. | [Analysis](../scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-15T120040+0800-3fd3c695.md) |
| 8 | Pigeon | Strengthen memory and personal-fact guidance; tighten repair hints. | 2/3 | 2/4 | Memory still ignored. Invented tenure removed; duties still inferred. | [Analysis](../scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-15T120805+0800-6376c45a.md) |
| 9 | Pigeon | Require explicit assessment of each boundary memory. | 2/3 | 2/4 | Boundary corrected; search lost scene context and revised reply failed review. | [Analysis](../scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-15T122235+0800-5f222af5.md) |
| 10 | Pigeon | Preserve exact scene context alongside requested quotation. | 3/3 | 4/4 | Correct passage and complete quote released after interpretation repair. Minor wording limitations remain. | [Analysis](../scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-15T123138+0800-1078d64b.md) |

Rounds 3 and 7 reused the preceding implementation to test a different scenario. Every other round had a distinct source digest.

Before round 10, the offline suite passed 1,426 tests and 589 subtests. These counts describe the pre-cleanup implementation.

Open follow-up issues are `linger-ecxr` for final-version live coverage, `linger-55r9` for wrong-passage Provenance approval, and `linger-zba5` for unsupported personal details in suggested wording. The paired Provenance diagnostic was validated offline but never run live.

[Machine-readable run index](2026-09-15-ten-rounds.json) retains source digests, adopted-input hashes, and recorded grades. Reports remain beside their original scenarios, including failed runs. The Main scenario retains its historical `packages/` location.
