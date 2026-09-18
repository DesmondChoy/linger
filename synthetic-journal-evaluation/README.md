# Synthetic evaluation scenarios

This directory retains one definition for each unique scenario. A scenario contains a Backstory, Ground truth, a pre-generation report, and an adoption record when independently approved.

## Evaluation retention scope

Cleanup applies only to evaluation artifacts introduced by branch `mlsp`,
identified by the changes from upstream `e780c31` to integrated `4eefd21`.
Evaluations that already existed upstream are retained unchanged, including
historical Kitchen, Pigeon, quotation, and Roses attempts.

Within `mlsp`, retain only the latest completed attempt for each unique test
that used the current implementation. None of its saved live attempts used the
post-rebase implementation at `c92dde1`. The cleanup therefore removes 88
`mlsp` attempt, report, log, and index files. No new live evaluation ran.

The 36 evaluation files outside `mlsp` are present with their original bytes.
Their historical results do not establish current-implementation coverage.
Removed `mlsp` outputs remain recoverable from Git commit `4eefd21`.

## Retained evaluations outside mlsp

| Scenario | Preserved historical artifacts |
| --- | --- |
| [Kitchen](scenarios/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/) | One replay transcript. |
| [Quotation](scenarios/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/) | All eight replay transcripts. |
| [Pigeon](scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/) | Twenty replay, analysis, summary, and follow-up files. |
| [Roses](scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/) | All seven connection replay transcripts. |

## Saved scenarios

The nine saved scenarios below keep their original input and adoption bytes. Similar Objectives do not make scenarios duplicates: their Lines, Props, and expected responses differ. The current-result column concerns the post-rebase implementation; historical evaluations outside `mlsp` remain available above.

| Scenario | Schema | Independent adoption | Current live result |
| --- | --- | --- | --- |
| [Cross-source connections and restraint](scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/) | Valid | Recorded | Not run |
| [Alice Caterpillar grounding and spoilers](scenarios/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/) | Historical; incompatible with current schema | Recorded | Not run |
| [Alice identity connections and restraint](scenarios/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/) | Valid | Missing | Not run |
| [Alice kitchen spoiler boundary](scenarios/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/) | Historical; incompatible with current schema | Recorded | Not run |
| [Alice Pigeon grounding and spoilers](scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/) | Valid | Recorded | Not run |
| [Alice quotation grounding](scenarios/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/) | Historical; incompatible with current schema | Recorded | Not run |
| [Alice roses, concealment, and restraint](scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/) | Valid | Recorded | Not run |
| [Pottery memory curation](scenarios/pottery-memory-curation--sculptor--2026-08-29/) | Valid | Recorded | Not run |
| [Reviewed capture and bounded curation](scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-13/) | Valid | Recorded | Not run |

The historical Caterpillar, quotation, and kitchen scenarios require explicit schema migration and fresh adoption of changed Ground truth before a graded replay. Cleanup did not migrate them. The identity-connection scenario validates but has no adoption record.

Saved scenarios live under `scenarios/`. Folder names use `<scenario-name>--<agents>--<YYYY-MM-DD>`; names identify the complete Scene set rather than one attempt.

## Five-book grounding and clarification

The five Scenarios generated on September 16, 2026 cover all registered books. Each now has four Scenes: grounded reflection without memory, personal reflection without book retrieval, memory-supported spoiler inference, and clarification of ambiguous reading progress. Human review on September 17 requested the separation of grounding from memory input. All five validate against the current contracts. Independent human adoption is recorded for all five revised Scenarios.

Each adopted Scenario ran once on September 17 with `openai:gpt-5.6-luna`. The recorded result is 14 of 20 Scenes passed: Alice 3/4, Animal Farm 3/4, Pinocchio 2/4, Douglass 3/4, and Keller 3/4. All five completed without execution errors and reported successful Logfire flushes. The [evaluation report](reports/five-book-replay-2026-09-17/evaluation-report.md) links every run, Logfire evaluation, and per-Scene analysis. It separates Pinocchio's unsafe Chapter 26 disclosure from unnecessary clarification and exact support-set mismatches. No optional semantic judge or rerun was invoked.

| Book | Backstory | Ground truth source | Adoption | Planning report |
| --- | --- | --- | --- | --- |
| Alice’s Adventures in Wonderland | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| Animal Farm | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| The Adventures of Pinocchio | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| Narrative of the Life of Frederick Douglass | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| The Story of My Life | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |

Douglass and Keller use section catalogs. The evaluator now reads them through the same corpus reader as production, preserving literary chapter numbers and excluding front matter, letters, and other parts from chapter-scoped evidence.


## Definitions and tooling

[Scenario descriptions](scenario_descriptions.md) explain the expected behavior. [The Objective catalog](evaluation-objectives.yaml) defines evaluation goals. [Generation presets](generation-presets/) remain shared inputs. None of these files is a live evaluation result.

The [evaluation guide](../evals/synthetic_journals/README.md) documents review and replay. The [run-scenario skill](../.agents/skills/run-scenario/SKILL.md) checks schema compatibility, adoption, model selection, and credentials before a live call.

Scenario validation uses no provider calls:

```bash
uv run python -m evals.synthetic_journals.validate_scenario \
	synthetic-journal-evaluation/scenarios/<scenario-name>/backstory.json \
	synthetic-journal-evaluation/scenarios/<scenario-name>/ground-truth.json
```

Adoption hashes establish which source bytes were approved. They do not establish a passing replay or compatibility with the current runtime.
