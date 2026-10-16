# Scenario run handoff

Updated 16 October 2026, Singapore time. Handoff for collecting final report and
slide evidence: **16 Scenarios and 79 source Scenes**.

## Current progress

**3 / 16 final results retained; 13 remain unrun.** Final results may include
legitimate failures. Follow each summary link for findings and next steps.

Scores count Scenes. **Completed** means the run and its LLM-review finished,
even when individual Scenes failed.

| Scenario | Scenes | Status | Automated | LLM-review | Summary |
| --- | ---: | --- | --- | --- | --- |
| [Alice event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Completed | 4/4 passed | 3/4 passed, 1 failed | [Summary](event-led-book-grounding-and-clarification--muse-librarian-provenance--2026-09-16/summary.md) |
| [Animal Farm event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Completed | 3/4 passed, 1 failed | 4/4 passed | [Summary](animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/summary.md) |
| [Pinocchio event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/pinocchio-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | - | - | - |
| [Douglass event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/douglass-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | - | - | - |
| [Helen Keller event-led grounding and clarification](../synthetic-journal-evaluation/scenarios/helen-keller-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16/backstory.json) | 4 | Not run | - | - | - |
| [Alice Pigeon grounding and spoilers](../synthetic-journal-evaluation/scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/backstory.json) | 3 | Not run | - | - | - |
| [Alice roses, concealment, and restraint](../synthetic-journal-evaluation/scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/backstory.json) | 3 | Not run | - | - | - |
| [Cross-source connections and restraint](../synthetic-journal-evaluation/scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/backstory.json) | 3 | Not run | - | - | - |
| [Pottery memory curation](../synthetic-journal-evaluation/scenarios/pottery-memory-curation--sculptor--2026-08-29/backstory.json) | 5 | Completed | 5/5 passed | 5/5 passed | [Summary](pottery-memory-curation--sculptor--2026-08-29/summary.md) |
| [Reviewed capture and bounded curation](../synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/backstory.json) | 16 | Not run | - | - | - |
| [Memory curation and cross-source connections](../synthetic-journal-evaluation/scenarios/memory-curation-and-cross-source-connections--muse-librarian-serendipity-sculptor-provenance--2026-09-19/backstory.json) | 9 | Not run | - | - | - |
| [Session continuity and longitudinal retrieval](../synthetic-journal-evaluation/scenarios/session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18/backstory.json) | 4 | Not run | - | - | - |
| [Memory injection and matched recall controls](../synthetic-journal-evaluation/scenarios/memory-injection-retrieval-controls--muse-serendipity-provenance--2026-09-29/backstory.json) | 2 | Not run | - | - | - |
| [Direct Line attacks and memory capture](../synthetic-journal-evaluation/scenarios/line-attack-response-and-capture--muse-provenance--2026-10-01/backstory.json) | 4 | Not run | - | - | - |
| [Sensitive inference and capture veto](../synthetic-journal-evaluation/scenarios/sensitive-inference-and-capture-veto--muse-provenance--2026-09-19/backstory.json) | 5 | Not run | - | - | - |
| [Supper club curation, then recall](../synthetic-journal-evaluation/scenarios/supper-club-curation-then-recall--muse-serendipity-sculptor-provenance--2026-09-30/backstory.json) | 5 | Not run | - | - | - |

## Run policy

- Use [run-scenario](../.agents/skills/run-scenario/SKILL.md) for selection, model
  confirmation, prerequisite checks, execution, and review. Run sequentially
  with the user and retain **one completed, reviewed result per Scenario**.
- Keep legitimate model failures. Propose fixes for confirmed prompt, code, or
  grader defects, then replace the affected result after a fix and rerun. Do not
  repeat a valid run just to obtain a pass. Keep the previous result if a rerun
  is incomplete.
- Keep the 16 Scenarios and approved expectations fixed. Record outdated
  expectations as limitations. After shared code changes, check earlier results
  for impact. Report single-run observations without repeatability claims.
- Keep `openai:gpt-6-luna`: low reasoning by default; medium for Serendipity,
  Muse draft and revision, and Provenance candidate review. Supper club retains
  its preset's internal repetitions and 60 recall cases in one invocation.

When sharing results after each run, give separate **Automated** and
**LLM-review** pass and fail totals, and name the Scenes that passed or failed.
Show inconclusive, unreviewed, and incomplete results explicitly.

For every failure, including an automated pass that fails LLM-review, record
the following in that run's `summary.md` and explain it to the user:

- **Ground truth.** State the approved expected behaviour and cite the relevant
  expectation or source passage. Show the actual result or decisive excerpt.
- **Failure type.** Use **legitimate model failure** when adequate instructions,
  inputs, and functioning code were available but the model made an error.
  Use **prompt failure** for unclear, contradictory, or incorrect instructions.
  Use **code failure** for implementation, orchestration, validation, or grader
  defects. Identify setup or provider failures separately.
- **Root cause.** Explain where the result first diverged from the expectation,
  with supporting trace, prompt, or code evidence. State whether the cause is
  confirmed or suspected. Use **inconclusive** when evidence cannot establish
  the cause, and name the next diagnostic check.
- **Proposed solution.** Recommend a specific change or future model comparison,
  explain why it addresses the cause, and say how to verify it. For legitimate
  model failures, retain the current result and propose improvements for a
  future comparison. Distinguish proposals from fixes already implemented.

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
