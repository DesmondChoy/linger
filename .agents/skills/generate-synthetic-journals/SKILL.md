---
name: generate-synthetic-journals
description: Select and confirm Linger evaluation objectives, inspect current implementation readiness, and write an implementation-oriented target-state report with a proposed generator prompt. Use when a developer wants to plan synthetic journal evaluation data without generating a dataset or invoking generation models.
---

# Generate Synthetic Journals

Use `synthetic-journal-evaluation/evaluation-objectives.yaml` as the sole source
of evaluation-objective text, composition rules, and prompt boundaries. Never
copy that content into this skill.

## Select objectives

1. Read the complete catalog and confirm that it contains exactly ten unique
   `evaluation_objectives`.
2. Resolve `scripts/objective_selector.py` relative to this `SKILL.md` and run it
   with the repository's Python environment as a long-running local process.
   Surface the printed `OBJECTIVE_SELECTOR_URL` as a clickable link and wait for
   the process to finish. Do not use a harness-native choice tool or accept a
   conversational objective selection. If the first launch exits with status 3
   and prints `OBJECTIVE_SELECTOR_BIND_PERMISSION_REQUIRED=127.0.0.1`, retry the
   exact command once through the harness's narrow approval or elevation
   mechanism for local binding. Keep the approved retry bound to `127.0.0.1`;
   never use a non-loopback host, disable the sandbox, or ask the developer to
   change global security settings.
3. The selector is the complete selection and confirmation surface. It displays
   all ten objectives together, grouped by `menu_families`. A resting card shows
   only the objective's icon and `menu.title`; hovering or focusing it reveals
   `menu.selection_hint`, `menu.summary`, and its
   `composition.combines_well_with` partners. The selector accepts one through
   all ten objectives, shows the live selection count, surfaces every
   `selection_constraints` rule on the affected card before it is violated, and
   confirms the complete selection.
4. Continue only after the process exits successfully with exactly one
   `CONFIRMED_SELECTION_JSON` record. Verify its catalog identifier and SHA-256
   against the catalog read in step 1, then use its ordered `objective_ids`.
   Never repair, deduplicate, or infer a selection outside the selector.

If approval is denied or unavailable, the one approved retry fails, the selector
cannot present its URL, it times out, its catalog fingerprint differs, or the
process exits without a valid confirmation record, stop and report that exact
failure. Do not retry any error other than the explicit bind-permission signal.
Confirmation does not start generation.

## Inspect current and target state

Confirmation authorizes read-only analysis and one Markdown report. It does not
authorize synthetic-data generation.

1. Record the selected Objective IDs and titles.
2. Snapshot the current repository with the branch, `HEAD` commit, dirty or clean
   status, local timestamp, and a concise fingerprint of materially relevant
   files. If the tree is dirty, identify materially relevant changes and state
   whether `HEAD` alone reproduces the inspected implementation. Inspect `HEAD`
   and up to five earlier commits that touch the selected Objectives' materially
   relevant specification, runtime, evaluation, contract, or test paths. Read
   the relevant diffs, not only their subjects, and record the commit hashes that
   establish or change the inspected workflow.
3. Read the selected Objectives' complete catalog entries. Inspect the current
   implementation, focused tests, existing `evals/` contracts, and relevant
   open and closed Beads for their declared agents, supporting components,
   mandatory gates, deterministic services, prompt inputs, and observable
   outcomes. Read each relevant Bead rather than relying on list output; closed
   work may be the best evidence for recently shipped behavior. Follow a linked
   issue, pull request, or commit when it is needed to understand that behavior.
   Read the five-agent architecture and shared authority boundaries in
   `docs/specification.md`. Distinguish implemented, partial, missing, and merely
   proposed behavior.
4. Reconcile the catalog, current specification, recent relevant commit diffs,
   production runtime path, Objective-specific evaluation runner, focused tests,
   and relevant open and closed Beads before judging readiness. Use the catalog
   as authority for Objective text, composition, and prompt boundaries; use the
   maintained specification, current code, and tests to describe shipped product
   behavior; and treat a runner as evidence only for the path it actually
   executes. The confirmed Objective defines the evaluation boundary. A runner
   is narrower only when it omits behavior that Objective requires, not merely
   because the product continues through later stages. Do not silently edit an
   Objective or let an actually narrower runner descope it. Name every material
   contradiction. An unresolved contradiction affecting the selected plan is a
   **source gap**: mark the implementation insufficient and set the fenced prompt
   to **Target state — do not run** with reconciliation as a precondition.
5. Trace every required Scene from setup through all participating agents,
   authority gates, deterministic services, state changes, and verification to
   its terminal product outcome for architectural context. Include applicable
   short-circuit and no-change branches. Then identify the selected Objective's
   evaluation endpoint separately. Do not add downstream product invariants to
   generator-authored Ground truth or grading unless the catalog or a separate
   adopted scope decision requires them. State which complete product path
   exists and which portion the current evaluation runner intentionally covers.
6. Read Section 7.2.1 completely and use its six canonical nouns exactly:
   `Objective`, `Backstory`, `Prop`, `Scene`, `Line`, and `Ground truth`. Use
   implementation terms such as `batch` only for actual runtime objects, never
   as replacements for canonical nouns.
7. Read the complete academic source
   `docs/submissions/aas-practice-module-briefing.pdf`. Use its project questions
   and expected artifacts to make one concrete academic-relevance claim. Do not
   invent a professor requirement or present a suggested design as mandatory.
8. Decide whether the target Backstory should be corpus-backed or memory-only.
   If book material is useful, point the future generator to `data/corpus/` and
   require it to discover the available work, immutable version, structure, and
   evidence at invocation time. Never hardcode corpus facts from an earlier
   report. If book material is not useful, do not require corpus inspection.
9. Describe the complete target evaluation design required by the confirmed
   Objectives, regardless of current implementation gaps. Keep one Backstory for
   one person and one evaluation account. Every Prop, Scene, and Line belongs to
   that Backstory. Props are separate records positioned before their designated
   Scenes; runtime-created records are outcomes, not Props. Lines are only
   conversational inputs sent to Muse. Workflow controls are not Lines.
10. Assess current implementation sufficiency for every required Scene. A Scene is
   **runnable** only when its setup can be supplied, its input has an existing
   execution path, required authority gates operate, its outcome is observable,
   and focused tests or an eval harness prove the relevant contract. Mark a Scene
   **partially runnable** when a named adapter or grading path is missing. Mark it
   **blocked** when a required capability or source is missing. Missing downstream
   freezing or replay alone does not weaken the target design; report the gap.
11. Inspect the package models in
   `evals/synthetic_journals/models.py` and deterministic validator in
   `evals/synthetic_journals/validate_package.py`. Use them unchanged. The
   `backstory.json` represents one Backstory, Props, Scenes, Lines, and offline
   inputs. The separate `ground-truth.json` contains proposed Ground truth
   anchored to those identifiers, exact spans, evidence, per-Scene Prop
   relevance judgments, and Scene pairings.
   Do not propose a parallel schema or claim that validation adopts Ground truth.
   If the selected Objectives cannot be represented, report a contract gap and
   stop the fenced prompt from authorizing generation.
12. Resolve run-specific workflow inputs. When
    `reviewed_automatic_memory_capture` is selected, use
    `synthetic-journal-evaluation/run-configurations/reviewed-automatic-memory-capture-10-to-1.json`
    unless the developer explicitly supplied another adopted configuration.
    Treat its 1:10 capture mix as this run's configuration, not a catalog-wide
    minimum. The package contains one Backstory; a full capture dataset repeats
    the 11-Scene pattern in separately validated packages with different
    Backstories.
    When `longitudinal_memory_retrieval` is selected, use
    `synthetic-journal-evaluation/run-configurations/longitudinal-memory-retrieval-10-to-1.json`
    unless the developer explicitly supplied another adopted configuration.
    Treat its 1:10 mix as a retrieval Prop constraint, not a Scene ratio or a
    universal requirement. The two retrieval Scenes share the same 11 active
    Props. Proposed Ground truth marks exactly one as relevant in the target
    Scene and all 11 as distractors in the comparison Scene, using one
    `GroundTruthProposal.prop_relevance` entry for every available Prop in each
    Scene. Without this Objective, create only the Props required by the
    confirmed selection.
13. Draft the exact target-state prompt for a future generator. Build it from the
    selected Objectives' `generation_brief`, permitted repository paths, resolved
    workflow inputs, translated Ground truth requirements, and the Backstory and
    Ground truth contracts. The prompt must explicitly instruct the
    generator how to produce the Backstory, Props or no Props, Scenes, Lines or
    offline inputs, and separate proposed Ground truth required by the plan. It
    must write `backstory.json` and `ground-truth.json` beside the report in the
    same package directory. Do not weaken or descope a confirmed Objective because
    current code is incomplete.
14. Put a precondition header inside the fenced prompt. If every Scene is
    runnable, label the prompt **Runnable after human approval**. Otherwise
    label it **Target state — do not run** and name every capability or source
    that must exist first. The detached prompt must remain
    self-invalidating when its prerequisites are unmet.
15. Obey `prompt_boundary`: do not send raw `composition`, `prompt_inputs`, or
    `evaluation_metadata`, numeric thresholds, judge rubrics, component routes,
    or the report itself to the generator. Evaluation-aware generation is
    intentional: translate the selected requirements needed to create a coherent
    Backstory, Scenes, and proposed Ground truth, while keeping grading and label
    adoption outside the generator. State that the generator has read-only access
    to the current checkout and must inspect permitted paths at invocation time.
16. Preserve the three-stage Ground truth lifecycle. First, require the generator
    to write proposed Ground truth in `ground-truth.json`, separate from
    `backstory.json`. Second, run the adopted package validator for objective
    facts including schema conformance, Backstory hashing, reference and
    span resolution, ordering, permitted evidence, declared matched-Scene
    differences, complete Prop relevance judgments, and resolved
    run-configuration counts; these checks do not judge whether the proposed
    relevance is semantically correct or assess Linger's recorded behavior.
    Third, require a reviewer independent of
    the generator to adopt, revise, or reject each candidate label. Only adopted
    Ground truth may grade a run, and neither proposed nor adopted Ground truth
    may reach the system under evaluation.
17. Hypothesize representative inputs, likely response behavior, and plain-
    language success checks. Treat response text as a hypothesis, not an exact
    oracle.

For a book-backed spoiler scenario, preserve the target two-phase design. The
complete current work is available only to a boundary-inference phase that
cross-references a Prop and Line and returns a typed candidate ceiling without
later-story content. A second phase retrieves evidence only at or before that
ceiling. The current reader-confirmed chapter flow does not satisfy this target;
mark the affected Scene blocked until event-led inference exists.

## Write the pre-generation report

Create exactly one package directory under
`synthetic-journal-evaluation/packages/`. Name it with the local timestamp
produced by `%Y-%m-%dT%H%M%S%z`; if it exists, append `-02`, `-03`, and so on. For
an isolated test, use the package directory supplied by the caller instead.
Write the Markdown report to `pre-generation-report.md` inside that directory.
The report is the only file this skill creates. Its fenced generator prompt must
use the same directory as `PACKAGE_DIRECTORY` and reserve exactly two sibling
output paths: `backstory.json` and `ground-truth.json`.

Before drafting, invoke `$google-developer-docs-style` when available and follow
it. If unavailable, read the relevant current official guidance under
`developers.google.com/style/`.

Write a decision memo followed by an implementation appendix. Limit narrative
prose to 900 words, excluding Markdown tables and fenced prompt blocks. Use
direct, conversational language, active voice, sentence-case headings, short
paragraphs, compact paths, and PDF page citations. Use the following sections
in order:

1. **Decision.** State whether the current implementation is **sufficient** or
   **insufficient** for the complete selected plan and give the practical
   consequence. Include a compact table with one row per required Scene or
   coherent ordered Scene sequence: target behavior, status (`runnable`,
   `partially runnable`, or `blocked`), and exact evidence or gap. Describe the
   Objective's evaluated outcome. Mention the terminal product outcome only as
   context, and do not treat downstream stages as evaluation gaps unless the
   confirmed Objective requires them.
2. **Your selection.** Use one short bullet per selected Objective with its
   title, ID, and a plain-language summary derived only from `menu.summary`.
3. **Target evaluation design.** Link `docs/specification.md` Section 7.2.1 at
   the first canonical-noun reference. From the default package directory, use
   `../../../docs/specification.md#721-canonical-vocabulary`; for an isolated
   test, use the equivalent relative link. Follow it with a compact two-column
   table containing exactly six body rows in this order: `Objective`,
   `Backstory`, `Prop`, `Scene`, `Line`, and `Ground truth`. Explain how each noun
   applies, including catalog minimums and any separately resolved run
   configuration.
   Describe the Backstory and Ground truth contracts directly, cite their
   model and validator paths, and explain their concrete structures. Explain
   proposed versus adopted Ground truth in the final row.
4. **Current implementation and required work.** Use **Observed**, **Proposed**,
   and **Assumed** labels. Cite implementation and focused-test evidence. Name
   reusable `evals/` assets, including the adopted package validator, the recent
   commits that establish or change the workflow, and relevant open and closed
   Beads. State the reconciled product path, the Objective evaluation endpoint,
   and current runner coverage. Do not call an intentionally downstream product
   stage a gap. For each actual gap, state whether it is a contract, capability,
   adapter, grading, or source gap; give the smallest high-level build-out and
   testable acceptance criteria. If authorities conflict, identify the exact
   conflict and the evidence needed to resolve it. If no build-out is required,
   say so. End this section with one compact repository snapshot line; do not
   create a separate Provenance section.
5. **Expected behavior and evaluation.** State whether the plan contains Lines
   or offline inputs. Pair each representative input with likely behavior and a
   plain-language success check. Put metric names after the explanation only
   when useful.
6. **Proposed generator prompt.** Include the exact prompt in a fenced code block.
   It must contain its own status and preconditions, direct instructions to use
   the Backstory and Ground truth contracts and validator, generation
   instructions for every generator-owned canonical entity, and instructions
   for a separate `ground-truth.json` containing proposed Ground truth. It must
   not ask the generator to grade recorded system
   behavior or claim that its candidate labels are adopted.
7. **Ground truth lifecycle.** Explain what the generator proposes, what
   repository code validates, and who independently adopts, revises, or rejects
   each label. Specify required evidence, exact spans, failure conditions, and
   acceptance checks. State explicitly that semantic realism and label quality
   are review judgments, not deterministic checks. If review ownership or
   tooling is not adopted, label that gap and propose the smallest decision
   needed.
8. **Architecture and academic relevance.** Identify participating and non-
   participating agents and deterministic services. Explain one authority
   boundary that the plan tests and make one concrete briefing-backed claim.

Do not add `Risks and opportunity` or `Provenance` sections. End with a **Human
decision required** callout. If implementation is sufficient, offer approval of
the target design and prompt, revision, or abandonment. If insufficient, offer
approval of the build target and target-state prompt, revision, or abandonment;
never offer execution before the named preconditions are met.

The report is only for the human or developer and must never be sent wholesale
to a generator. Do not invoke a generation model or create Backstories, Props,
Scenes, Lines, offline inputs, Ground truth files, proposed or adopted Ground
truth, annotations, packages, frozen releases, or replay data.

After writing the report, resolve `scripts/validate_report.py` relative to this
`SKILL.md` and run it with the repository's Python environment, passing every
confirmed ID as a separate `--objective-id`. If it reports an error, revise the
report and rerun the validator until it exits successfully. Do not estimate the
word count. Then verify the semantic requirements that the script cannot prove:

- Every required Scene has one current status with concrete evidence or a gap.
- Every Scene is traced to its terminal product outcome for context, including
  applicable authority gates, deterministic services, state changes,
  verification, and short-circuit branches. The report separately states the
  Objective evaluation endpoint and current runner coverage.
- Generator-authored Ground truth and grading stop at the confirmed Objective's
  evaluation boundary unless a separate adopted scope decision expands them.
- The report reconciles the catalog, maintained specification, recent relevant
  commit diffs, runtime, evaluation runner, focused tests, and relevant open and
  closed Beads, and cites the commits and Beads that materially affect readiness.
- Every unresolved material contradiction is named as a source gap, makes the
  plan insufficient, and appears as a **Target state — do not run** precondition.
- The target design satisfies every confirmed Objective without descoping.
- The fenced prompt uses the package models and validator without inventing
  another contract.
- The fenced prompt creates proposed Ground truth in a separate
  `ground-truth.json` without grading recorded behavior or claiming adoption.
- Deterministic validation and independent Ground truth adoption are concrete in
  the human report.
- Exactly one Backstory, person, and evaluation account are used; every Prop,
  Scene, and Line belongs to that Backstory; and every Prop has a planned
  lifecycle role.
- Every adopted run configuration for the confirmed Objectives appears in
  `run_configuration_ids` and its exact entity counts are translated into the
  fenced prompt. For longitudinal retrieval, both Scenes share the same 11
  active Props and proposed relevance covers all 11 Props in each Scene.

Report the path and selected Objective IDs, then stop. The repository defines
the Backstory and Ground truth contracts and deterministic validator.
This skill does not authorize generation. After separately authorized generation
writes the two JSON files, `$review-synthetic-ground-truth` owns independent
review, adoption, and the handoff to an implemented Objective-specific replay.
Full-dataset assembly, package freezing, and unsupported replay paths remain
unadopted until separately approved.
