# Scenario run handoff

Updated 16 October 2026, Singapore time. Handoff for collecting final report and
slide evidence: **16 Scenarios and 79 source Scenes**.

## Current progress

**3 / 16 final results retained; 13 remain unrun.** Animal Farm awaits separate
publication. Final results may include legitimate failures. Follow the published
summary links for findings and next steps.

| Scenario | Scenes | Current result | Final runs / target |
| --- | ---: | --- | ---: |
| [Alice event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | [Final; 4/4 automated, 3/4 LLM-review](event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/summary.md) | 1 / 1 |
| [Animal Farm event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Final locally; awaiting publication | 1 / 1 |
| [Pinocchio event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | 0 / 1 |
| [Douglass event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | 0 / 1 |
| [Helen Keller event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | 0 / 1 |
| [Alice Pigeon grounding and spoilers](../synthetic-journal-evaluation/scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/backstory.json) | 3 | Not run | 0 / 1 |
| [Alice roses, concealment, and restraint](../synthetic-journal-evaluation/scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/backstory.json) | 3 | Not run | 0 / 1 |
| [Cross-source connections and restraint](../synthetic-journal-evaluation/scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/backstory.json) | 3 | Not run | 0 / 1 |
| [Pottery memory curation](../synthetic-journal-evaluation/scenarios/pottery-memory-curation--sculptor--2026-08-29/backstory.json) | 5 | [Final; 5/5 automated, 5/5 LLM-review](pottery-memory-curation--sculptor--2026-08-29/summary.md) | 1 / 1 |
| [Reviewed capture and bounded curation](../synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/backstory.json) | 16 | Not run | 0 / 1 |
| [Memory curation and cross-source connections](../synthetic-journal-evaluation/scenarios/memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19/backstory.json) | 9 | Not run | 0 / 1 |
| [Session continuity and longitudinal retrieval](../synthetic-journal-evaluation/scenarios/session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18/backstory.json) | 4 | Not run | 0 / 1 |
| [Memory injection and matched recall controls](../synthetic-journal-evaluation/scenarios/memory-injection-retrieval-controls--muse-serendipity-provenance--2026-09-29/backstory.json) | 2 | Not run | 0 / 1 |
| [Direct Line attacks and memory capture](../synthetic-journal-evaluation/scenarios/line-attack-response-and-capture--muse-provenance--2026-10-01/backstory.json) | 4 | Not run | 0 / 1 |
| [Sensitive inference and capture veto](../synthetic-journal-evaluation/scenarios/sensitive-inference-and-capture-veto--muse-provenance--2026-09-19/backstory.json) | 5 | Not run | 0 / 1 |
| [Supper club curation, then recall](../synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/backstory.json) | 5 | Not run | 0 / 1 |

## Run policy

- Use [run-scenario](../.agents/skills/run-scenario/SKILL.md) for selection, model
  confirmation, prerequisite checks, execution, and review. Run sequentially
  with the user and retain **one completed, reviewed result per Scenario**.
- Keep legitimate model or prompt failures. Fix confirmed application or grader
  defects and replace the affected result after rerunning. Mark uncertain causes
  **inconclusive**. Keep the previous result if a rerun is incomplete.
- Keep the 16 Scenarios and approved expectations fixed. Record outdated
  expectations as limitations. After shared code changes, check earlier results
  for impact. Report single-run observations without repeatability claims.
- Keep `openai:gpt-6-luna`: low reasoning by default; medium for Serendipity,
  Muse draft and revision, and Provenance candidate review. Supper club retains
  its preset's internal repetitions and 60 recall cases in one invocation.

## Storage and reporting

Keep two files per Scenario. `summary.md` holds run findings, failure diagnoses,
follow-up decisions, report and slide points, and Logfire links. `result.json`
holds structured outcomes and the original captured evidence. Keep this README
to shared guidance and the status table, linking to each run's summary.

**Automated** means the runner's implemented checks. **LLM-review** means the
coding assistant's assessment against the full request and approved expectations
after the run. It is separate from Linger's runtime agents and human validation.

Use the skill's bundle and report commands to publish at `results/<scenario>/`.
Replace superseded local results and update this table. Preserve original inputs
and grades. For comparisons, save baseline settings and scores in the report
before replacing traces. Local JSON supports extraction; Logfire adds the span
tree and timings. Replacing local results leaves older Logfire experiments intact.
