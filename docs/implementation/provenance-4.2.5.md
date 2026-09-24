# Provenance 4.2.5 replay findings

## Scope

The first three runs below exercised the original adopted prerequisite Scenario for
`reviewed_automatic_memory_capture` and `bounded_memory_curation`. They did
not exercise the complete 4.2.5 conversational target. In particular, they did
not run the later fresh-chat surfacing flow required by
`proactive_memory_surfacing`.

The Scenario used one adopted Backstory, one evaluation account, 11 capture
Scenes, and five Props-only curation Scenes. Each run used the same adopted
Ground truth and the production combined replay runner.

The runs used the original adopted Ground truth. The current proposed revision
now accepts the shorter durable span for `scene-capture-07` and expects the
evolving summary to use `prop-evolving-1` and `prop-evolving-3`. The old
adoption is stale after that revision. Fresh adoption is required before another
replay.

After those runs, the two Ground truth cases were revised, independently
adopted again, and replayed once more. The fourth run used the revised
expectations and passed all 16 Scenes.

## Results across the three runs

| Run | Capture Scenes | Curation Scenes | Total | Failed Scenes |
|---|---:|---:|---:|---|
| [Run 1](../synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/scenario-run-2026-09-22T221234+0800-capture-curation/evaluation.json) | 11/11 | 4/5 | 15/16 | `scene-curation-evolving` |
| [Run 2](../synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/scenario-run-2026-09-22T230737+0800-capture-curation-01/evaluation.json) | 10/11 | 4/5 | 14/16 | `scene-capture-07`, `scene-curation-evolving` |
| [Run 3](../synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/scenario-run-2026-09-22T230737+0800-capture-curation-02/evaluation.json) | 10/11 | 4/5 | 14/16 | `scene-capture-07`, `scene-curation-evolving` |

All 48 capture and curation Scene executions completed. No run failed because of a
provider or application exception. The two failing patterns were hard-gate
mismatches in recorded behavior.

The runs are visible in Logfire:

- [Run 1](https://logfire-us.pydantic.dev/keimi/starter-project/evals/reviewed_capture_and_bounded_curation/compare?experiment=01a0c973b2f1ba285a792da6c4025c1f-c19be7f06672f68a)
- [Run 2](https://logfire-us.pydantic.dev/keimi/starter-project/evals/reviewed_capture_and_bounded_curation/compare?experiment=01a0c9a8c541dd80e0085acce03aa4bf-29ba5b828e71626e)
- [Run 3](https://logfire-us.pydantic.dev/keimi/starter-project/evals/reviewed_capture_and_bounded_curation/compare?experiment=01a0c9aae4a4899861da010b225f233b-75217a80014e44e2)
- [Revised run](https://logfire-us.pydantic.dev/keimi/starter-project/evals/reviewed_capture_and_bounded_curation/compare?experiment=01a0d3b3d392a773b4f7213dffbd9219-f0c8f76dcf9ce97b)

The revised run is stored at
`synthetic-journal-evaluation/scenarios/reviewed-capture-and-bounded-curation--muse-sculptor-provenance--2026-09-21/scenario-run-2026-09-24T215551+0800-capture-curation/evaluation.json`.
All 16 Scenes passed hard gates. The capture and curation paths produced no
new hard-gate failure in that run.

## Failure case: `scene-capture-07`

The original adopted Ground truth expected Muse to nominate the complete Line:

```text
I have realised that sketching by hand helps me slow down and think clearly, so I want to keep Saturday mornings for it.
```

Run 1 nominated that complete span and passed the Scene. Runs 2 and 3 nominated the same meaningful inner sentence instead:

```text
sketching by hand helps me slow down and think clearly, so I want to keep Saturday mornings for it.
```

The recorded span was codepoint range 21–120. Provenance allowed the nomination,
the application bound it exactly to the Line, and storage committed it. The
runner still failed both later runs with:

- `nominated_span_mismatch`
- `stored_text_mismatch`

This is a model-behavior variance issue at the exact-span contract. The selected
memory is semantically close to the adopted label, but the replay requires the
stored text to match the adopted span exactly. The first run shows that the
runtime can produce the adopted full-span behavior. The later runs show that
the current prompt and model do not produce it consistently.

## Failure case: `scene-curation-evolving`

The Scene supplies three records that refine one evolving fact and one unrelated
bus-delay record:

- `prop-evolving-1`: a short walk clears the person's head.
- `prop-evolving-2`: the person prefers walking without headphones.
- `prop-evolving-3`: the person now takes a quieter riverside path to reset.
- `prop-evolving-noise`: a bus was late.

The original adopted Ground truth expected `update_derived_summary` using the
first three Props and excluding the bus-delay record. The revised proposal uses
the two Props that the first run actually treated as the evolving fact:
`prop-evolving-1` and `prop-evolving-3`.

Run 1 returned an `update_derived_summary` proposal using only
`prop-evolving-1` and `prop-evolving-3`. The curation loop applied the
summary, Provenance allowed it, and all source Props remained unchanged. The
runner failed `source_memory_ids_mismatch` because the proposal omitted
`prop-evolving-2`.

Runs 2 and 3 returned `assign_topic_group` instead of the expected
`update_derived_summary`. The application applied the topic group over all
four supplied Props, including the unrelated bus-delay record. Provenance
allowed the proposal and source hashes remained unchanged, but the runner
failed:

```text
expected_action:update_derived_summary;got:assign_topic_group
```

This is both an action-selection and source-selection instability. The first run
chose the right action but an incomplete source set. The later runs chose the
wrong action and included noise. The application preserved source records in all
three runs, so the failure is about curation quality and Ground truth alignment,
not destructive storage behavior.

## What this establishes

The prerequisite capture and bounded-curation path is wired end to end and
produces durable traces, adoption identities, Provenance decisions, storage
outcomes, and source hashes. It is not yet stable enough to serve as clean
release evidence:

- Exact capture spans can vary across provider runs.
- Evolving-fact curation is not reliably separated from topic grouping.
- The curation application and source-preservation controls remained intact in
  the failing runs.
- These results do not establish the complete 4.2.5 conversational path,
  because no later fresh-chat surfacing and release Scene ran.

The two revised cases now pass. The remaining 4.2.5 work is the complete
conversational replay. An adopted `proactive_memory_surfacing` Scenario must
exercise later fresh-chat surfacing, Provenance review, and final release.
