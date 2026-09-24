# Five-book evaluation, September 17, 2026

All five adopted Scenarios ran once with `openai:gpt-5.6-luna`. The deterministic result is **14 of 20 Scenes passed**. Every run completed without recorded execution errors and reported `flushed: true` for Logfire. No replay or optional semantic-judge call was added.

The most consequential failure is Pinocchio's ambiguous school detour. The application granted Chapter 26 without enough reader evidence and disclosed the later episode. Its Provenance review passed because the answer matched the retrieved passage; that does not establish permission to disclose the passage.

## Recorded results

| Book | Scenes passed | Detailed review | Run artifact | Logfire |
| --- | --- | --- | --- | --- |
| Alice | 3/4 | [Read](alice-analysis.md) | [JSON](alice.json) | [Open evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af342f22972e6a36a229d1dc2113-4853ae601cc6cf49) |
| Animal Farm | 3/4 | [Read](animal-farm-analysis.md) | [JSON](animal-farm.json) | [Open evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af3710f7821e3d80fbd6f0b4de46-31885624f8f1295a) |
| Pinocchio | 2/4 | [Read](pinocchio-analysis.md) | [JSON](pinocchio.json) | [Open evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af3ab4729a3f16850da320625390-ec1afc944b2cb582) |
| Douglass | 3/4 | [Read](douglass-analysis.md) | [JSON](douglass.json) | [Open evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af3df43915573afa4993023b7b2b-353a09ef1b957cb3) |
| Helen Keller | 3/4 | [Read](keller-analysis.md) | [JSON](keller.json) | [Open evaluation](https://logfire-us.pydantic.dev/kevinmanuellee/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a0af4257becd47f321e958dfba3fe7-f8b03f194b6d7e5a) |

The official failures remain unchanged. Artifact review distinguishes unsafe disclosure, unnecessary clarification, and sufficient evidence that differs from an adopted exact support set.

## Findings across the five books

Pinocchio's ambiguous Scene supplied two possible episodes, Chapters 9 and 26. Both reached the boundary model. The model nevertheless treated "another decision" as proof of the later episode, granted Chapter 26, and released the Shark outing and companions. This needs a boundary decision fix, not a quotation fix.

Alice, Douglass, and Keller failed their event-based progress inference. Each asked for the latest completed chapter instead of establishing the expected ceiling. The artifacts record `insufficient_context` with no boundary-inference model exchange. This is consistent with the current-Line search returning no usable evidence before memory search and judging. Raw rankings are absent, so the precise retrieval cause remains unproven.

Animal Farm and Pinocchio inferred the correct ceilings, Chapters 5 and 9. Both failed only the exact boundary-support requirement. Their retained evidence supports those ceilings, including the stopping event. These are official contract failures with semantically sufficient alternative proof, rather than observed unsafe ceilings. A future evaluation change needs deliberate review; this report does not revise adopted labels.

All ten grounding and personal-reflection Scenes passed their hard checks. Those checks do not establish complete response quality. Pinocchio supplied the requested quotation but omitted the requested literary comparison. Alice changed the terminal punctuation in one extra quoted fragment. The personal-reflection controls avoided book retrieval.

Four of five ambiguous-progress Scenes safely clarified. Alice's boundary model received only one of the two authored bottle candidates. Douglass and Keller clarified through an insufficient-context fallback. Those passes demonstrate withholding, but do not prove that the runtime compared both alternatives. Animal Farm did receive both authored alternatives.

## Every Scene

| Book and Scene | Hard result | Artifact review |
| --- | --- | --- |
| Alice: `alice-race-reflection` | Pass | Exact requested Dodo quotation and useful thimble comparison; one additional fragment changes terminal punctuation. |
| Alice: `alice-personal-comparison` | Pass | Useful response about appreciation and shared responsibility; no book retrieval. |
| Alice: `alice-spoiler-inference` | Fail | Generic clarification despite a specific Chapter 3 stopping event; no inferred scope or memory support. |
| Alice: `alice-bottle-ambiguity` | Pass | Safe clarification; only the Chapter 1 candidate reached the boundary model. |
| Animal Farm: `farm-decision-reversal` | Pass | Exact quotation and supported workplace comparison, without assigning the lead Napoleon's motives. |
| Animal Farm: `farm-personal-trust` | Pass | Practical request for consultation; no book retrieval. |
| Animal Farm: `farm-spoiler-inference` | Fail | Correct Chapter 5 ceiling and sufficient stopping-event proof; omits one adopted support span. |
| Animal Farm: `farm-interrupted-discussion` | Pass | Both authored alternatives reached the model; clarification released no later plot. |
| Pinocchio: `pinocchio-promises-and-book` | Pass | Exact requested quotation, but misses the imagined-coat versus actual-sale comparison. |
| Pinocchio: `pinocchio-personal-study` | Pass | Manageable study commitment and acknowledgement of help; no book retrieval. |
| Pinocchio: `pinocchio-spoiler-inference` | Fail | Correct Chapter 9 ceiling with sufficient proof; selected support differs from the adopted set. |
| Pinocchio: `pinocchio-school-detour` | Fail | Unjustified Chapter 26 permission; disclosed the seashore, Shark, and companions instead of clarifying. |
| Douglass: `douglass-grounded` | Pass | Exact Chapter 7 quotation and practical comparison that preserves the historical difference. |
| Douglass: `douglass-personal` | Pass | Concrete follow-up on unresolved requests; no book retrieval or inferred motives. |
| Douglass: `douglass-spoiler-inference` | Fail | Generic clarification despite the copybook stopping event; no Chapter 7 ceiling. |
| Douglass: `douglass-uncertain` | Pass | Safe clarification through retrieval fallback; comparison of the two returns is unproven. |
| Keller: `keller-grounded` | Pass | Exact Chapter 10 concluding sentence and supported reflection on care, possession, and another person's choices. |
| Keller: `keller-personal` | Pass | Practical ways to let the sister choose; no book retrieval. |
| Keller: `keller-spoiler-inference` | Fail | Generic clarification instead of the Chapter 10 stopping point. |
| Keller: `keller-uncertain` | Pass | Safe clarification; no recorded boundary model comparison of the alternatives. |

## Scope and evidence

Each Scenario contains four fresh Scenes. The grounding and personal-reflection Scenes have no memory Props. The two spoiler Scenes have their own Props to test progress inference and ambiguity. This follows the human correction that grounded book reflection does not require memory.

The production path includes Provenance release checks. Animal Farm's grounded Scene also invoked Serendipity against the same bounded book source. The selected Objectives remain `grounded_book_reflection` and `spoiler_boundary_clarification`; the artifact records the actual calls made.

Keller's section identifiers are not literary chapter numbers. Section 011 contains Part I, Chapter IX; section 012 contains Part I, Chapter X. Front matter causes the offset. The Chapter 10 crab passage is therefore correctly stored in section 012. Douglass's Chapter VII similarly maps to section 10. The explicit-chapter grounding Scenes retrieved these sources correctly.

The five run artifacts match their adopted Ground truth identities and contain exactly the expected four Scene IDs each. The preparation changes passed 79 focused contract and replay tests. No runtime or Ground truth edits were made in response to these live results.

The per-book reviews linked above assess replies and traces independently of the generator. They are artifact analysis, not another provider-backed semantic grade. Recorded semantic spoiler checks remain `not_run`. A successful Logfire flush is recorded locally; remote visibility was not independently checked.

The saved [manifest](manifest.json) identifies the approved inputs and run paths. [Results](results.json) retain all deterministic failures and Logfire links. Original output files were generated in a fresh temporary directory and copied here byte-for-byte, with SHA-256 hashes in [artifact hashes](artifact-hashes.json).

## Follow-up work

- `linger-rt2x`, priority 1: fix unsupported Chapter 26 permission in Pinocchio's ambiguous Scene.
- `linger-hwxg`, priority 2: diagnose missing candidate retrieval for event-based progress inference.
- `linger-42d3`, priority 2: review exact support-set grading and gaps in complete reflection checks.

These issues record findings only. No additional provider runs, commits, or pushes were performed.
