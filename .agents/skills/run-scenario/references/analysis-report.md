# Analysis rubric and report contract

The developer needs to decide whether the evaluation ran, whether the scenario
still makes sense, how much to trust each result, and what to change next. Apply
this rubric to every run. The review is analysis by the coding agent, not an
additional model-based grader or a replacement for recorded Ground truth grades.

## Use the saved facts

Read the `analysis_data` JSON returned by the helper. It contains `summary`, all
`scenes` in scenario order, `telemetry`, detailed `evidence`, and `review: null`.
Fill only `review`. Use the typed expectations, actual Scene results, original
evaluation artifact, and current scenario files. Follow evidence references when
an excerpt cannot answer a review question. Read current grading code before
claiming that a particular behavior was checked.

Keep execution, automated results, and interpretation separate. An execution
error does not demonstrate an application behavior failure. A passing grade
does not establish semantic quality. Missing observations are inconclusive;
they do not establish that work never ran. An ungraded Scene is not a pass.
For blocked preflight, assess scenario readiness and mark behavior as unexercised.
Missing, duplicate, or unexpected Scene results prevent a complete evaluation
even when every available grade passes. Preserve valid observed grades and
explain the coverage problem; do not call the scenario successful.

The renderer controls these sections and their order:

1. **Outcome:** execution, counts, verdict, and whether the goal, inputs, and
   Ground truth remain appropriate. Keep model and date compact.
2. **Scene results:** every Scene's recorded status, expected behavior, and
   observed behavior, in scenario order.
3. **Scene analysis:** why each result occurred, assessment, confidence, grade
   reliability, and a Scene-specific next step.
4. **Next steps:** ordered changes or diagnostic checks with observable
   verification criteria.
5. **Evidence:** links to the saved evaluation, Logfire, and detailed evidence.

Aim for a short report with roughly 80–150 words of analysis per Scene. Cover all
Scenes even when that requires more than one page. Include only decisive quotes,
observations, or causal changes. Leave full JSON, logs, hashes, scripts, file
inventories, and broad Git history in the linked evidence.

## Analyze the reason for every grade

For each Scene, answer these questions in its structured review fields:

- What behavior is this Scene meant to distinguish? State the expected action
  and relevant prohibited behavior in ordinary language.
- What actually happened? Name the decisive response, route, tool result,
  retrieval, release, or storage observation. Include a short excerpt only when
  its wording matters.
- Why did the recorded checks pass or fail? Connect the observation to the
  actual checks. If an earlier decision prevented the intended behavior from
  running, explain that limit instead of treating each downstream failure as
  an independent defect.
- Does the current input provide the information needed for the expected
  answer? Does the Ground truth still follow current requirements? Distinguish
  scenario drift, an application defect, a grader defect, setup failure, and
  insufficient evidence. Scenario age and commit lists alone prove none of these.
- How trustworthy is this grade? For a pass, consider a potential false
  positive. For a failure, consider a potential false negative. State the
  specific evidence and remaining uncertainty.
- What is the next useful action, and what would establish that it worked?
  If no correction is supported, say so rather than inventing work.

For passing Scenes, explicitly check whether the intended path was exercised,
the assertions discriminate the desired behavior, and the observed output meets
the parts of the expectation the grader omits. A pass caused by an empty/default
result, an early return, missing evidence, or a generic response deserves closer
inspection. In a negative control, deliberately avoiding a tool may be exactly
the expected behavior; verify the rest of the response before criticizing the
absence of a call. Check paired Scenes when available to assess whether the
system can distinguish the intended cases.

For example, a no-retrieval check alone cannot establish a useful personal
reflection. A clarification label alone cannot establish that the question
addresses the missing information. A valid curation schema alone cannot prove
that the proposed grouping is appropriate. These are coverage questions, not
automatic evidence that the observed output is wrong. Read the actual response
and checks before assigning a suspected false positive.

## Use consistent assessments

Keep the recorded grade unchanged. Use one assessment per Scene:

| Assessment | Use when |
| --- | --- |
| `credible_pass` | The observed behavior supports the passing checks within the stated evaluation scope. No material concern was found. |
| `pass_with_limitations` | The observed pass is supported, but a meaningful part of the intended behavior is ungraded or unverified. State that gap. |
| `potential_false_positive` | Specific evidence suggests the passing checks can conceal a failure of the intended behavior. Explain the mechanism and how to confirm it. |
| `supported_failure` | An observed mismatch is a valid failure under the applicable expectation. State whether the correction belongs to the scenario, application, or evaluator. |
| `potential_false_negative` | Specific evidence suggests a failed grade rejects behavior acceptable under the intended requirement. Inspect the expectation or grader before prescribing a fix. |
| `inconclusive` | Available evidence cannot support a behavioral judgment. Name what is missing. |
| `not_exercised` | The intended behavior was not reached or the run never started. Explain what prevented it. |

Use `confirmed` for an interpretation established by the saved observations and
relevant code or a performed local probe. Use `likely` when a specific hypothesis
has evidence but alternatives remain. Use `unresolved` when the deciding evidence
is missing. Confidence describes the interpretation, not a calibrated probability
or a guarantee that a future evaluation will pass.

## Write the structured review

The authoritative schema is `AnalysisReview` in
`evals/synthetic_journals/scenario_analysis.py`. The JSON `review` object contains:

```json
{
  "verdict": "A concise conclusion and its immediate implication.",
  "scenario_assessment": {
    "goal": "Whether the Objective still tests useful behavior.",
    "input_validity": "Whether the inputs establish the conditions needed by the expectation.",
    "ground_truth_validity": "Whether the expected behavior still follows current requirements."
  },
  "confidence": "confirmed",
  "scenes": [
    {
      "scene_id": "copy-the-exact-scene-id",
      "expected_behavior": "The behavior required by this Scene.",
      "observed_behavior": "The decisive observation from this run.",
      "interpretation": "Why that observation explains the recorded grade.",
      "assessment": "pass_with_limitations",
      "confidence": "confirmed",
      "evidence_refs": ["copy-a-real-evidence-reference-from-this-report"],
      "grade_reliability": "Why the grade is credible, or a specific misleading-result risk and coverage gap.",
      "next_step": "A justified action or an explicit statement that no correction is indicated."
    }
  ],
  "next_steps": [
    {
      "target": "investigation",
      "action": "A concrete change or diagnostic check.",
      "verification": "The observable result that would resolve the issue."
    }
  ]
}
```

Replace the example prose and include every actual Scene exactly once. The
renderer preserves scenario order. `evidence_refs` must identify facts or files
actually read, such as the supplied Scene evidence reference, a saved evaluation
field, or a relevant source line. Do not fabricate support or copy example IDs.
The renderer checks coverage and compatible assessment labels; the skill must
check that the reasoning is supported by the cited evidence.

Next-step targets are `scenario`, `application`, `evaluator`, `configuration`,
`observability`, or `investigation`. Order them by dependency and impact. Name
the smallest correction and its acceptance criteria. When diagnosis is
unresolved, choose the next discriminating check and explain what its possible
outcomes imply. An empty next-step list is appropriate when no corrective action
is warranted. Do not weaken Ground truth merely to obtain green results.

If a scenario needs revision, recommend a successor scenario, validation, and
fresh independent adoption before another confirmed run. When an expectation
still applies and the application violates it, recommend an application fix.
Any local probe used in analysis must be reported as such; it does not prove a
subsequent live run will pass. Analyze the current artifacts without adding API
calls, rerunning the evaluation, or editing adopted authority files.

Before a local probe, trace the concrete runtime service and configuration used
by the replay. A lexical retrieval baseline cannot reproduce a hybrid retrieval
result. A narrower probe can establish a shared routing branch, but its limits
must be explicit when interpreting other stages. Prefer existing observations
when reproducing the actual runtime would require an unapproved provider call.

## Finish the report

Run the `report --analysis` command from the skill. It validates that review is
complete and renders Markdown deterministically from the saved data. Read the
output once for unsupported claims, missing pass commentary, generic next steps,
and evidence that overwhelms the result. Correct the structured review and render
again when needed; do not hand-edit generated Markdown or append a second report.

Keep remote Logfire visibility separate from SDK export success. A saved URL or
`flushed: true` is not a read-back check. If remote access is unavailable, say so
without treating telemetry access as a failure of the Scene's behavior.

The same saved facts and review produce the same Markdown. The rubric, labels,
and validation make fresh-context reports comparable, but a different LLM may
write different prose or identify a different supported hypothesis. Preserve
uncertainty instead of forcing agreement with a previous report.
