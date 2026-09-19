# Synthetic evaluation scenarios

This directory retains one definition for each unique scenario. A scenario contains a Backstory, Ground truth, a pre-generation report, and an adoption record when independently approved.

## Saved scenarios

Each Scenario directory contains its source and review records. The directories
retain no replay transcripts, run summaries, or analysis reports. A recorded
adoption identifies approved inputs; it does not establish a passing execution.

The following table lists saved designs outside the five-book set below.
Scenarios with similar Objectives remain distinct because their Lines, Props,
and expected responses differ.

| Scenario | Schema | Independent adoption |
| --- | --- | --- |
| [Cross-source connections and restraint](scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/) | Valid | Recorded |
| [Alice Caterpillar grounding and spoilers](scenarios/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/) | Incompatible with current schema | Recorded |
| [Alice identity connections and restraint](scenarios/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/) | Valid | Missing |
| [Alice kitchen spoiler boundary](scenarios/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/) | Incompatible with current schema | Recorded |
| [Alice Pigeon grounding and spoilers](scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/) | Valid | Recorded |
| [Alice quotation grounding](scenarios/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/) | Incompatible with current schema | Recorded |
| [Alice roses, concealment, and restraint](scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/) | Valid | Recorded |
| [Pottery memory curation](scenarios/pottery-memory-curation--sculptor--2026-08-29/) | Valid | Recorded |
| [Reviewed capture and bounded curation](scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-13/) | Valid | Recorded |
| [Sensitive inference and capture veto](scenarios/sensitive-inference-and-capture-veto--muse-provenance--2026-09-19/) | Valid | Recorded |

The Caterpillar, quotation, and kitchen scenarios require schema migration and fresh adoption of changed Ground truth before a graded replay. The identity-connection scenario validates but has no adoption record.

Saved scenarios live under `scenarios/`. Folder names use `<scenario-name>--<agents>--<YYYY-MM-DD>`; names identify the complete Scene set rather than one attempt.

## Five-book grounding and clarification

These Scenarios cover all registered books. Each contains four Scenes:
grounded reflection without memory, personal reflection without book retrieval,
memory-supported spoiler inference, and clarification of ambiguous reading
progress. All five validate against the current contracts and have independent
adoption records. Their exact inputs and expectations are linked below and
summarized in [Scenario descriptions](scenario_descriptions.md).

| Book | Backstory | Ground truth source | Adoption | Planning report |
| --- | --- | --- | --- | --- |
| Alice’s Adventures in Wonderland | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| Animal Farm | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| The Adventures of Pinocchio | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| Narrative of the Life of Frederick Douglass | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |
| The Story of My Life | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth.json) | [Recorded](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/ground-truth-adoption.json) | [Read](scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/pre-generation-report.md) |

Douglass and Keller use section catalogs. The evaluator reads them through the same corpus reader as production, preserving literary chapter numbers and excluding front matter, letters, and other parts from chapter-scoped evidence.

## Scenario preparation

The [session continuity and longitudinal retrieval plan](scenarios/session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18/pre-generation-report.md)
describes a four-Scene design with a continuity pair and a memory-retrieval pair.
It contains only a pre-generation report, with no Backstory, Ground truth,
adoption, or replay result. It remains preparation for generation and review,
separate from the saved Scenario definitions above.

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
