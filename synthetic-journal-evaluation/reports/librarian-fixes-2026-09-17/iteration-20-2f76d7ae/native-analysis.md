# Iteration20 native Scene review

All eight native evaluation processes completed and all29 Scenes were reviewed, including the two passing replies. Independent recomputation from their evaluation artifacts gives **2/29 Scenes and2/32 judgments passing**. This batch is dominated by provider failures and does not establish a semantic regression across27 Scenes. The original grades and adopted authority remain unchanged.

| Suite | Scenes | Judgments | Analysis |
| --- | --- | --- | --- |
| 4 Pigeon | 0/3 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/analysis-report-2026-09-18T194022+0800-df67154c.md) |
| 6 Roses | 0/3 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-18T194100+0800-4d0a9203.md) |
| 7 Farm | 0/4 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-18T194204+0800-5bff2ca5.md) |
| 8 Hume | 0/3 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-18T194156+0800-4cfef713.md) |
| 9 Douglass | 0/4 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-18T194221+0800-416804b9.md) |
| 10 Alice | 1/4 | 1/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-18T194312+0800-0c1ccf0e.md) |
| 11 Keller | 1/4 | 1/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-18T194258+0800-8af108ab.md) |
| 12 Pinocchio | 0/4 | 0/4 | [Reviewed report](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/analysis-report-2026-09-18T194315+0800-da66a4fa.md) |

Assessments: **27 inconclusive,1 credible pass,1 potential false positive**. All eight analysis JSON files validate as AnalysisDocument; every Scene remains in order and its full review text appears in the rendered report. The index now contains **127 unique native reports**, preserving the preceding119 entries.

## Provider failures and actual coverage

The27 nonpassing Scenes each contain explicit provider HTTP429. Across native agent exchanges,33 failures report failure_category=provider_error and provider_status_code=429:16 emotional preflights,10 Muse drafts,2 book requests,2 Serendipity searches,1 boundary inference,1 evidence-strength review and1 Provenance review. No other failure category occurs in these native exchanges. Some represent a failed nested call and its enclosing draft, so33 exchange failures is not a count of independent root incidents.

Pigeon never gets beyond emotional preflight in any Scene. Roses reaches successful preflight for its two source-dependent Scenes, but Muse and one nested discovery call fail; its personal control fails preflight. Farm's specific inference reaches a Muse clarification draft after book planning and boundary inference fail, then Provenance also fails; all other Farm Scenes fail preflight. Hume has no successful draft. Douglass has two successful preflights but no draft or boundary review. Alice's explicit response fails at draft with failed planning, strength and discovery calls; its specific inference fails preflight and its ambiguous control fails draft. Keller's book answers fail draft and ambiguous control fails preflight. Pinocchio's explicit answer fails draft and all other Scenes fail preflight.

There is **no successful Librarian boundary candidate, independent event-identification call, chapter grant or released book answer**. Neither the positive nor negative event gate is exercised. Farm's subject-fidelity repair, complete event-inventory repair and the approved Douglass optional support cannot be assessed live from this batch. Failed grades naming missing evidence, wrong boundaries or missing quotations are downstream consequences of these failed provider calls, not evidence that the canonical passages or approved expectations became wrong. All27 affected Scenes release only the application temporary-error decline and no evidence.

## The two released personal controls

**Keller is a credible pass.** The response offers consent-first questions, optional arrangements and practical tasks chosen by the sister. Possible unintended effects remain tentative and follow the reader's stated concern. It introduces neither book/memory assertions nor invented completed actions.

**Alice is a qualified potential false positive.** Its recognition-versus-work distinction and practical request are useful. However, the proposed first-person script says the reader carries the organizing and upfront cost “alone.” The current Line says the reader organizes the lunches and usually pays the deposit; it does not establish exclusive responsibility for all organizing. This strengthens the supplied account into a factual premise in suggested speech. Its test also changes both appreciation and practical help before treating relief as evidence of a stronger need. The wording is tentative, and this is less severe than a false book quotation or asserted diagnosis, but it remains a personal-reflection assumption the mechanical pass and independent review do not catch. No reader motive should be treated as established from that hypothetical.

## Integrity and limits

Each scenario's current authority bytes matched its saved launch hashes before its review was populated. Root's approved Douglass optional pit passage is part of iteration20's launch authority; this review makes no further Ground truth or adoption change. Only analysis review fields, rendered reports, this synthesis and report index entries were written. No source or provider calls were changed or repeated, and no iteration beyond20 was attempted.

Remote Logfire traces were not opened. Local telemetry metadata cannot independently establish complete remote trace availability. The other four suite types have separate reviews; these native counts must not be presented as batch-wide counts or as evidence that all fixes passed. The last authorized live iteration is exhausted, with these infrastructure limits and the remaining semantic concern explicitly retained.
