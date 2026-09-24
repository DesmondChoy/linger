# Farm boundary proof review

The iteration-3 Farm failure combines **one missing required anchor and one additional valid passage**. The boundary still correctly locates chapter 5 and releases the requested in-scope quotation. Unlike the extra-only Pigeon, Alice and Pinocchio failures, accepting additional evidence alone would not resolve Farm’s recorded failure. No runtime, adopted expectation or provider call changed during this review.

## What happened

The reader explicitly describes the dogs chasing Snowball, recognizing them as the puppies, the end of debates, the subsequent windmill reversal, and stopping after the tactics explanation is accepted while the dogs growl. The saved memory independently describes Napoleon taking the puppies away earlier. The current Line identifies the final stop without needing the recognition bridge to disambiguate it.

Both recognition windows, `ch05-ln1082-1103` and `ch05-ln1096-1114`, occur in the saved twenty-candidate input. The model copies the complete recognition clause into `event_resolution.reader_event_spans`, but places both windows in `other_evidence_ids`. Its selected occurrence contains `ch05-ln1160-1185` and `ch05-ln1177-1203`; the latter includes the entire final tactics/acceptance stop. The memory assessment cites `ch03-ln0694-0721`. A later windmill rebuilding passage in chapter 6 is explicitly ruled out using the reader’s first-build reversal and tactics details. This is proof selection after retrieval, not missing retrieval or lost query decomposition.

Evidence: [saved boundary exchange](iteration-03-4715c97d/suite-7.json), `scenes[2].agent_exchanges[3]`; its final output is at lines 3394–3469, including the copied recognition clause at line 3424 and excluded recognition window at line 3458. The input contains both recognition candidates. Its only repair requested two missing inventory IDs, not inclusion of the recognition bridge in support. The final answer and its separate actor-wording limitation are recorded in the native Farm report and [repair-3-design.md](repair-3-design.md).

## Why the current contract permits this proof

The [boundary skill](/Users/kevinmanuel/Documents/REPO/linger/src/linger/agents/librarian/skills/boundary-inference/SKILL.md:81) distinguishes candidate inventory from authorization support and requests the needed current-event and memory anchors. It explicitly allows a completed sequence to end in a later chapter (line 96). The memory section (lines 154–183) requires independently grounded prior knowledge, a coherent current report, and a separately located final event. It does not require every intermediate event in the reader’s narrative to be individually cited.

[Typed validation](/Users/kevinmanuel/Documents/REPO/linger/src/linger/agents/librarian/models.py:344) checks exact reader spans, complete candidate inventory, canonical selected-event chapter and inclusion of selected-event evidence. Memory validation (line 432) additionally requires every grounded memory’s evidence in boundary support. These checks do not prove semantic coverage of every clause. The [application](/Users/kevinmanuel/Documents/REPO/linger/src/linger/orchestration/boundary.py:405) repeats validation and checks identity, chapter bounds and authorization. No independent omitted-bridge rule exists.

The model’s declared reason and selected spans show focus on the final stop; its internal reason for omitting the bridge is not observable. The current contract explains why the omission is accepted. The retrieved recognition passage confirms the reader’s account is consistent, but the model’s minimal support set does not make that bridge auditable by citation. This is a real omission relative to the adopted three-anchor requirement, not evidence that chapter 5 is unsafe or incorrectly inferred.

## Exact offline grading probe

The probe used the current compiler and matcher against saved artifacts, without retrieval or model execution. The matcher requires coverage in both directions: each adopted span must match an actual canonical record, and every actual record must match an adopted span. See [book_replay.py](/Users/kevinmanuel/Documents/REPO/linger/evals/synthetic_journals/book_replay.py:1144).

| Check | Result |
| --- | --- |
| Required puppies-taken | Covered by `ch03-ln0694-0721` |
| Required puppies-recognised | Missing |
| Required tactics-acceptance | Covered by `ch05-ln1177-1203` |
| Extra actual record | `ch05-ln1160-1185` |
| Actual recorded set | False |
| Remove extra only | False |
| Add recognition only | False |
| Add recognition and remove extra | True |

Reproduction from repository root:

```python
import json
from pathlib import Path
from evals.synthetic_journals.validate_scenario import validate_scenario_files
from evals.synthetic_journals.book_contract import compile_book_replay_plan
from evals.synthetic_journals.book_replay import (
    BookSceneObservation, _evidence_matches, _evidence_sets_match,
)
base = Path("synthetic-journal-evaluation")
scenario = base / "scenarios/animal-farm-event-led-grounding-and-clarification--muse-librarian-provenance--2026-09-16"
backstory, ground_truth = validate_scenario_files(
    scenario / "backstory.json", scenario / "ground-truth.json"
)
scene = next(s for s in compile_book_replay_plan(backstory, ground_truth).scenes
             if s.scene.scene_id == "farm-spoiler-inference")
artifact = base / "reports/librarian-fixes-2026-09-17/iteration-03-4715c97d/suite-7.json"
observed = BookSceneObservation.model_validate_json(
    json.dumps(json.loads(artifact.read_text())["scenes"][2])
)
expected = tuple(scene.evidence_by_id[k] for k in (
    "farm-puppies-taken", "farm-puppies-recognised", "farm-tactics-acceptance"
))
actual = observed.boundary_support_evidence
without_extra = tuple(r for r in actual
                      if any(_evidence_matches(e, r) for e in expected))
recognition = next(r for r in scene.evidence_by_id[
    "farm-puppies-recognised"
].accepted_runtime_records if r.evidence_id.endswith("ln1096-1114"))
for records in (actual, without_extra, (*actual, recognition),
                (*without_extra, recognition)):
    print(_evidence_sets_match(expected, records))
# False, False, False, True
```

This counterfactual tests the matcher only. It neither modifies the saved result nor establishes that a later model run will select another set.

## Decision needed

Keep the recorded failure. Human review must decide whether all three named anchors are intentionally required, or whether independently grounded prior knowledge plus the uniquely identified final stop meets the intended requirement. Approval to accept extra evidence does not answer this separate question. The current adopted prose explicitly names all three anchors; it must not be silently narrowed.

A possible future general improvement is to make explicit identity or causal bridges used in a progression argument auditable with reader-span-to-evidence mappings, and to check the entire reported sequence for material contradiction. However, requiring every earlier event solely to satisfy this gold would change the present authority contract and introduce avoidable false negatives. No such runtime change is recommended on this run alone. Preserve the distinction between absent corroboration and actual contradictory evidence; personal asides and incidental details need not become mandatory book retrieval targets. Any future contract change should test valid multi-chapter sequences, material contradictions, and unneeded or unretrieved incidental clauses, alongside bridge completeness.

Confidence: confirmed for the saved omission, correct chapter, available candidates and matcher behavior; the necessity of the three-anchor proof is an unresolved human expectation decision.
