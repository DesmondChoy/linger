# Synthetic evaluation scenarios

This directory retains one definition for each unique scenario. A scenario
contains a Backstory and proposed Ground truth. Planning reports record the
generation design where present; adoption records identify independently
approved inputs.

## Saved scenarios

The checked-in Scenario definitions contain their source and review records.
Guided runs create separate run directories and analysis reports beside those
sources. A recorded adoption identifies approved inputs; it does not establish
a passing execution.

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
| [Reviewed capture and bounded curation, September 13](scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-13/) | Valid | Recorded |
| [Reviewed capture and bounded curation, September 21](scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/) | Valid | Recorded |
| [Memory curation and cross-source connections](scenarios/memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19/) | Valid | Recorded |
| [Session continuity and longitudinal retrieval](scenarios/session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18/) | Valid | Recorded |
| [Memory injection and matched recall controls](scenarios/memory-injection-retrieval-controls--muse-serendipity-provenance--2026-09-29/) | Valid | Recorded |
| [Direct Line attacks and memory capture](scenarios/line-attack-response-and-capture--muse-provenance--2026-10-01/) | Valid | Recorded |
| [Sensitive inference and capture veto](scenarios/sensitive-inference-and-capture-veto--muse-provenance--2026-09-19/) | Valid | Recorded |
| [Supper club curation, then recall](scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/) | Valid | Recorded |

The Caterpillar, quotation, and kitchen scenarios require schema migration and
fresh adoption of changed Ground truth before a graded replay. The
identity-connection scenario validates but has no adoption record.

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

## Memory and security scenarios

The session-continuity and longitudinal-retrieval scenario combines a continuity
pair with a memory-retrieval pair. The supper-club scenario uses the
`memory-curation-recall-loop` configuration to compare recall before curation
and after cumulative reviewed curation rounds. Combined capture-curation and
curation-connection scenarios preserve their component boundaries and use
production curation review.

Memory-injection controls pair a poisoned saved memory with the same source
after removing its attack span. Direct Line attacks pair reply and memory
attacks with clean controls and grade released replies separately from actual
stored records. Their
[replay contracts and commands](../evals/synthetic_journals/README.md#memory-injection-controls)
explain exposure checks, storage observations, and semantic-review limits.

## Definitions and tooling

[Scenario descriptions](scenario_descriptions.md) explain the expected behavior. [The Objective catalog](evaluation-objectives.yaml) defines evaluation goals. [Generation presets](generation-presets/) remain shared inputs. None of these files is a live evaluation result.

The [evaluation guide](../evals/synthetic_journals/README.md) documents review and
replay. The [run-scenario skill](../.agents/skills/run-scenario/SKILL.md) checks
schema compatibility, adoption, model selection, and credentials before a live
call. Inspect the saved scenario menu without calling a provider:

```bash
uv run python -m evals.synthetic_journals.run_scenario menu \
	--output /tmp/linger-scenario-menu.json
```

Use `inspect --menu PATH --number N` to read an entry, or `check` with the same
options to save a report when preflight is blocked. A run requires the user's
explicit provider and model confirmation.

Scenario validation uses no provider calls:

```bash
uv run python -m evals.synthetic_journals.validate_scenario \
	synthetic-journal-evaluation/scenarios/<scenario-name>/backstory.json \
	synthetic-journal-evaluation/scenarios/<scenario-name>/ground-truth.json
```

Adoption hashes establish which source bytes were approved. They do not establish a passing replay or compatibility with the current runtime.
