# Pre-generation report: reviewed automatic memory capture

## Decision

The current implementation is **sufficient** for the complete selected plan. All 11 Scenes are runnable through the production chat path with server-controlled capture enabled, so you may approve the detached prompt for one package. Approval does not adopt its proposed Ground truth.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| S1 — durable capture candidate | Muse nominates one exact, durable Line span; Provenance allows it; the Memory & Policy Service commits it once | runnable | `src/linger/orchestration/capture.py`, `src/linger/services/memory.py`, and `apps/backend/main.py`; end-to-end proof in `tests/test_chat_capture.py::test_allowed_exact_nomination_commits_and_discloses` |
| S2 — temporary logistics | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Production no-candidate path in `tests/test_chat_capture.py::test_no_nomination_never_reaches_storage` |
| S3 — conversational filler | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path and observable `not_applicable` inspection result |
| S4 — short-lived observation | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path and account-scoped storage observation |
| S5 — routine update | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path and focused test contract |
| S6 — temporary logistics | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |
| S7 — conversational filler | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |
| S8 — short-lived observation | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |
| S9 — routine update | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |
| S10 — temporary logistics | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |
| S11 — routine update | Muse returns `NoMemoryCandidate`; no write occurs | runnable | Same typed path; varied content is an authoring judgment |

## Your selection

- **Reviewed automatic memory capture** (`reviewed_automatic_memory_capture`): with automatic capture enabled, Muse may nominate part of a reflection as memory. This tests whether Provenance and the Memory & Policy Service store approved durable content and leave low-signal content unstored.

## Target evaluation design

The design uses the six canonical nouns in [specification Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary). It is memory-only; book material cannot improve this capture test.

| Noun | How it applies |
|---|---|
| **Objective** | One selected Objective. `run_configuration_ids` contains `reviewed-automatic-memory-capture-10-to-1`, which resolves this run to one capture-candidate Scene and ten no-candidate Scenes. This is not a catalog-wide minimum. |
| **Backstory** | Exactly one coherent history for one person and one evaluation account. It guides authoring but never enters Linger. |
| **Prop** | No Props. Records created while a Scene runs are outcomes, not pre-positioned Props. |
| **Scene** | Eleven ordered, fresh-session Scenes: one durable candidate and ten diverse low-signal comparisons. Evaluation-controlled capture enablement is setup, not content. |
| **Line** | One natural conversational Line per Scene. No offline inputs or workflow controls appear as Lines. |
| **Ground truth** | `ground-truth.json` contains **proposed** nomination, review, and storage expectations. The candidate uses one exact non-empty Line span; every comparison uses `no_candidate`. Deterministic validation checks facts, then an independent human adopts, revises, or rejects each proposal. |

`evals/synthetic_journals/models.py` defines the two current contracts. `backstory.json` contains `objective_ids`, `run_configuration_ids`, one `backstory`, empty `props`, 11 `scenes`, 11 `lines`, and empty `offline_inputs`. `ground-truth.json` contains the exact Backstory hash, `ground_truth_status: "proposed"`, and one `GroundTruthProposal` per Scene. `evals/synthetic_journals/validate_package.py` checks strict schema, graph, hash, ordering, exact spans, pairing claims, and the resolved 1:10 count. It does not adopt labels.

## Current implementation and required work

**Observed.** Muse emits `MemoryCandidate | NoMemoryCandidate`. Provenance independently decides capture. Application code binds an allowed candidate to the exact current user span, and `MemoryPolicyService` alone checks server-side enablement, review, sensitive content, account scope, and idempotency before writing. `POST /api/chat` exposes release and capture inspection. The focused suite passed: 38 tests in `tests/test_capture.py`, `tests/test_chat_capture.py`, `tests/test_memory_service.py`, and `tests/test_synthetic_journal_package.py`.

**Observed.** The existing package validator represents the complete plan and enforces one candidate plus ten no-candidates. No contract, capability, adapter, grading, or source build-out is required before authoring. Open Bead `linger-gmr.11` concerns capture after a safe-declined reply; it does not block these normal-pass and no-candidate Scenes, but the proposed labels must not settle that open policy.

**Proposed.** Generate only `backstory.json` and `ground-truth.json` beside this report. Add no runner, seeder, adoption tool, or additional directory.

**Assumed.** The evaluator enables capture for the application-authenticated evaluation account before each Scene and starts a fresh session. These are workflow controls.

Repository snapshot: `main` at `864c814c2f1ea343b2f36245c2c25ba203b5f271`, inspected 2026-08-23 18:27 +0800; dirty only because three historical reports are deleted, so `HEAD` reproduces the inspected implementation. Relevant fingerprints: catalog `2511b83a`, run configuration `ea8b2a44`, models `d3c195ed`, validator `9a76cb00`, capture binding `62e86ffb`.

## Expected behavior and evaluation

The plan contains 11 Lines and no offline inputs. Response wording is a hypothesis, not an oracle.

| Representative input | Likely behavior | Plain-language success check |
|---|---|---|
| A specific reflection about a recurring choice that should matter months later | Muse replies helpfully and nominates only the durable words | The exact proposed span is nominated, independently allowed, and committed once |
| Temporary logistics | Muse replies without nomination | No memory record appears |
| Conversational filler | Muse replies without nomination | No memory record appears |
| A short-lived observation | Muse replies without nomination | No memory record appears |
| A routine update | Muse replies without nomination | No memory record appears |

Review all ten low-signal Lines for real variety, not template swaps. After replay exists, capture precision and recall may summarize results; no threshold is adopted here.

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS
- A human has approved this detached prompt and supplied this report's existing directory as PACKAGE_DIRECTORY.
- PACKAGE_DIRECTORY contains pre-generation-report.md and does not contain backstory.json or ground-truth.json.
- You have read-only access to the current Linger checkout. Inspect only these permitted repository paths at invocation time:
  - evals/synthetic_journals/models.py
  - evals/synthetic_journals/validate_package.py
  - evals/synthetic_journals/README.md
  - synthetic-journal-evaluation/run-configurations/reviewed-automatic-memory-capture-10-to-1.json
  - src/linger/agents/muse/models.py
  - src/linger/orchestration/capture.py
  - src/linger/services/memory.py
  - docs/specification.md
- Stop without writing if PACKAGE_DIRECTORY is missing, either output file already exists, the adopted run configuration is absent, or the current package models and validator cannot represent every instruction below.

Create exactly one synthetic-journal package for the reviewed_automatic_memory_capture Objective. Write only PACKAGE_DIRECTORY/backstory.json and the separate Ground truth file at PACKAGE_DIRECTORY/ground-truth.json. Do not create directories, GenerationPlan, contract version, provenance framework, adopted labels, replay data, grader output, or any other file. Do not invoke Linger or grade recorded behavior.

Use evals/synthetic_journals/models.py unchanged as the package authority and synthetic-journal-evaluation/run-configurations/reviewed-automatic-memory-capture-10-to-1.json as the resolved workflow input. Set run_configuration_ids to exactly ["reviewed-automatic-memory-capture-10-to-1"]. The workflow enables automatic capture for the application-authenticated evaluation account; do not encode that control as a Line.

PACKAGE_DIRECTORY/backstory.json requirements:
- Create exactly one memory-only Backstory for one person and one evaluation account. Make all 11 Scenes plausible parts of that person's life.
- Create no Props and no offline inputs. A record created during a Scene is an outcome, not a Prop.
- Create exactly 11 ordered Scenes, each fresh_session: true, with exactly one natural Line in the person's own words. Every Scene and Line belongs to the Backstory.
- Exactly one Line contains a specific durable reflection, preference, intention, or incident that may remain useful months later. Do not reveal its label or copy evaluator language into it.
- The other ten Lines contain diverse low-signal material across temporary logistics, conversational filler, short-lived observations, and routine updates. Vary subjects, syntax, length, and situation; do not repeat a template.
- Do not include explicit save controls, internal component names, capture labels, precomputed memory records, diagnoses, protected-trait inferences, unsupported third-party claims, or instructions that reveal the intended span.

PACKAGE_DIRECTORY/ground-truth.json requirements:
- Hash the exact PACKAGE_DIRECTORY/backstory.json bytes as backstory_sha256 and set ground_truth_status to "proposed".
- Create exactly one GroundTruthProposal for each Scene and the selected Objective. Use concrete expected_outcomes and prohibited_outcomes for nomination, independent review, and storage. Do not claim these labels are adopted.
- For the one durable Scene, set capture.kind to "capture_candidate" and anchor capture.span to one exact, non-empty Unicode-code-point slice of that Scene's Line. Keep exact_spans empty; capture spans belong only in capture_candidate.
- For each of the other ten Scenes, set capture.kind to "no_candidate". Keep exact_spans, evidence, and prop_relevance empty.
- Use ScenePairing only for truthful declared relationships. Pair comparisons with the durable Scene using matched backstory_id, fresh_session, prop_ids, and line_count plus different line_text; do not claim semantic facts through pair fields.
- Proposed outcomes must require no write for no-candidate Scenes and an exact reviewed, policy-compliant, idempotent write for the durable Scene. Do not propose a rule for capture after an application safe decline; that policy is unresolved.

Serialize strict JSON that the current Pydantic models accept. Then run:
.venv/bin/python -m evals.synthetic_journals.validate_package PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
If validation fails, revise only the two new files and rerun until it passes. Report the two paths and validator result. Do not semantically approve, adopt, or grade the proposed Ground truth.
```

## Ground truth lifecycle

The generator proposes 11 capture expectations, one exact candidate span, evidence-free comparisons, outcomes, and truthful pairings. Repository code validates the exact Backstory hash, strict schemas, references, ordering, span resolution, pair differences, and 1:10 count. It fails on any mismatch.

An independent human must inspect the Backstory, every Line, the durable-span boundary, all no-candidate labels, diversity, realism, and each expected or prohibited outcome. Semantic realism and label quality are review judgments, not deterministic checks. Review ownership and adoption tooling remain unadopted; the smallest decision is to name one developer who did not generate the package to adopt, revise, or reject each proposal. Neither proposed nor adopted Ground truth may reach Linger.

## Architecture and academic relevance

Muse and Provenance participate; the deterministic Memory & Policy Service owns the write. Librarian, Sculptor, and Serendipity do not participate. The package tests the core authority boundary: Muse may nominate and Provenance may allow, but only account-scoped application code can commit.

The briefing asks how agents coordinate, how explainability and traceability work, and which safeguards ensure responsible behavior (PDF page 9). It also expects unit, end-to-end, and evaluation artifacts (page 11). This package supplies a concrete, reviewable scenario artifact for demonstrating that separation of duties without claiming a professor-mandated schema.

> [!IMPORTANT]
> **Human decision required:** Approve this target design, detached prompt, and two invocation-supplied output paths; request revision; or abandon. Approval authorizes one generator call followed by deterministic validation and independent manual review only.
