# Pre-generation decision memo

## Decision

The current implementation is **sufficient** for the complete selected plan. The mixed-Objective adapter now replays all three Scenes through production chat and grades the same deterministic gates against proposed or independently adopted Ground truth. You may use the prompt after human approval; approval does not adopt its proposed labels.

| Required Scene or sequence | Target behavior | Status | Exact evidence or gap |
|---|---|---|---|
| S1 — event-led grounded reflection | Use an active event-memory Prop and natural Line to infer a safe ceiling, retrieve only within it, and ground a quotation or factual claim | runnable | Production path in `src/linger/orchestration/boundary.py`, `src/linger/orchestration/grounding.py`, and `apps/backend/main.py`; mixed replay and ceiling/evidence grading in `evals/synthetic_journals/book_replay.py`, proven by `tests/test_synthetic_book_replay.py` |
| S2 — ambiguous book comparison | With the same event-memory Prop but an ambiguous Line, ask for clarification and retrieve no book evidence | runnable | `book_replay.py` observes the content-free inference handoff, exact clarification release, and absence of scope or retrieval; focused production-chat proof is in `test_production_chat_path_receives_props_but_not_ground_truth` |
| S3 — personal non-factual reflection | Respond usefully without unnecessary book retrieval | runnable | `book_replay.py` requires no boundary inference, grounding call, or released book evidence; the three-Scene replay test proves the isolated no-Prop comparison |

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`): distinguish a passage-backed quotation or factual claim from a personal reflection that needs no retrieval.
- **Spoiler-boundary clarification** (`spoiler_boundary_clarification`): infer progress from remembered events, stay within that ceiling, and clarify when the evidence is ambiguous.

## Target evaluation design

Use the six [canonical nouns](../../../docs/specification.md#721-canonical-vocabulary) as follows.

| Noun | Application |
|---|---|
| Objective | The two confirmed catalog entries govern one coherent three-Scene package; no run configuration applies. |
| Backstory | One corpus-backed reading history for one person and one evaluation account. |
| Prop | One separate, pre-positioned memory of a previously discussed event, active before S1 and S2 and absent from S3. |
| Scene | S1 combines unique boundary inference with grounded reflection; S2 is its ambiguous spoiler comparison; S3 is the non-factual grounding comparison. All start fresh sessions. |
| Line | One natural conversational input per Scene, sent only to the production chat boundary. |
| Ground truth | Separate proposals record safe ceiling, forbidden later fact, retrieval need, permitted corpus evidence, exact spans, pairings, and expected or prohibited outcomes. Deterministic validation does not adopt them; an independent human must adopt, revise, or reject them. |

`../../../evals/synthetic_journals/models.py` requires `backstory.json` to contain one `SyntheticBackstory` graph: selected IDs, no run configuration, one Backstory, one Prop with Scene lifecycle, three ordered Scenes, and three Lines. `ground-truth.json` contains one proposed `GroundTruthProposal` for every Scene/Objective pair, hashes the exact Backstory bytes, and uses typed grounded-reflection or spoiler-boundary expectations, repository evidence, exact Prop or Line spans, and Scene pairings. Repository evidence has a globally unique review `evidence_id`; replay matches its hash-bound exact text to observed production evidence without coupling the package to retrieval-window IDs. `../../../evals/synthetic_journals/validate_package.py` checks those structures.

## Current implementation and required work

**Observed.** Full-work, request-scoped boundary inference returns a typed content-free candidate or clarification; application code validates it and clamps a separate evidence search. Muse drafts, Provenance gates every candidate, and deterministic release checks resolve quotations and evidence. `book_replay.py` now validates the three-Scene topology, seeds active Props into isolated per-Scene storage, disables capture, calls production chat, records inference and grounding separately, and grades proposal or adopted labels without passing Ground truth into runtime. Fresh verification passed: 401 tests and 275 subtests, including 60 focused package, replay, adoption, review-app, and telemetry tests. Relevant Beads: `linger-s2d` tracks this report; `linger-ck1` tracks the completed implementation; `linger-dj6` is an unrelated open cache-key bug.

**Proposed.** No build-out is required before generation. Keep independent human adoption between deterministic package validation and any adopted evaluation run. Do not run evaluation while generating the two package files.

**Assumed.** A human independent of generation owns label review. The future generator discovers the current immutable corpus revision and evidence at invocation time.

Snapshot: `main` at `23ee593badde2878f4ec2a78a8e77fdfab72e318`, 2026-08-29T11:09:12+0800; relevant-file fingerprint `501151f1699dbef043e2152f0c14814560b7187ba46c96d212df11a6b1f46bfd`; the tree contains the material uncommitted replay, contract, validator, test, and documentation implementation, so `HEAD` alone does not reproduce the inspected behavior.

## Expected behavior and evaluation

The plan contains Lines, not offline inputs.

| Representative input | Likely behavior hypothesis | Plain-language success check |
|---|---|---|
| Event-memory Prop plus a request about a specific passage or claim | Infer the latest known event, retrieve within that ceiling, and answer with verified evidence | The ceiling matches the event; every quotation and claim resolves; nothing later is retrieved or disclosed |
| Same Prop plus a genuinely ambiguous event reference | Ask a focused, spoiler-safe clarification | No evidence search runs and the question reveals no later fact |
| Personal reflection related to the theme but making no book claim | Respond directly and helpfully | No book retrieval occurs and the response does not force book context |

Response wording is a hypothesis, not an exact oracle.

## Proposed generator prompt

```text
STATUS: Runnable after human approval

PRECONDITIONS: Generate only after a human approves this target design and prompt. The implemented mixed-Objective replay and grading path is present. Generation still creates proposed labels only; independent adoption remains a later human step.

PACKAGE_DIRECTORY=synthetic-journal-evaluation/packages/2026-08-29T095720+0800

You have read-only access to the current checkout. Inspect only data/corpus/, evals/synthetic_journals/models.py, and evals/synthetic_journals/validate_package.py at invocation time. Discover the available work, immutable version, ordered structure, and exact evidence from data/corpus/; do not rely on a book fact from an earlier report.

Use evals/synthetic_journals/models.py unchanged as the Backstory and proposed Ground truth contract. Use evals/synthetic_journals/validate_package.py unchanged as the deterministic package validator. Write exactly PACKAGE_DIRECTORY/backstory.json and PACKAGE_DIRECTORY/ground-truth.json. Do not write any other file.

Create one corpus-backed Backstory for one person and one evaluation account. Set objective_ids, in order, to ["grounded_book_reflection", "spoiler_boundary_clarification"] and run_configuration_ids to [].

Create exactly one Prop as separate source text about a previously discussed story event. Do not copy the Backstory into the Prop. Give the Prop an active lifecycle before the two book-boundary Scenes; do not assign it to the personal comparison Scene.

Create three ordered, fresh-session Scenes and one natural Line per Scene:
1. A combined event-led grounded reflection. The Prop and Line must uniquely support a safe reading ceiling without naming chapter coordinates. The Line must ask about a specific passage, quotation, or factual book claim that needs repository-backed evidence, while connecting it to a personal question.
2. An ambiguous spoiler comparison using the same active Prop. The Line must remain genuinely ambiguous and must not reveal later events or contain chapter coordinates; the intended behavior is a focused clarification before any evidence retrieval.
3. A nearby personal, non-factual reflection with no Prop. It must remain useful without book retrieval.

Every Prop, Scene, and Line must belong to the same Backstory, person, and evaluation account. Lines are conversational inputs only; do not encode setup, session reset, policy, expected routes, or grading labels as Lines. Runtime-created records are outcomes, not Props. Create no offline inputs.

Create a separate ground truth file at PACKAGE_DIRECTORY/ground-truth.json with ground_truth_status "proposed" and the SHA-256 of the exact PACKAGE_DIRECTORY/backstory.json bytes. Add one proposed GroundTruthProposal for every Scene/Objective pair required by the Scene graph. These are candidate labels, not adopted labels.

For the grounded pair, populate grounded_book_reflection with retrieval set to required or not_required. For required retrieval, list permitted_evidence_ids and any exact_quotation_evidence_ids. Record each permitted repository item with a globally unique evidence_id, current repository-relative path, exact UTF-8 code-point span, exact text, and source SHA-256. Use no evidence IDs for not_required. Pair the two Scenes with truthful match and difference fields.

For the spoiler pair, populate spoiler_boundary with decision infer or clarify, authorised_prop_ids, the event-derived safe_ceiling_chapter only for infer, supporting_evidence_ids only for infer, and at least one forbidden_later_evidence_id for both. Every referenced item must be repository evidence with its own globally unique evidence_id. Add exact Prop and Line spans that carry event evidence. Pair the unique and ambiguous Scenes and record expected and prohibited outcomes so later disclosure, post-ceiling retrieval, or clarification that leaks the forbidden fact fails review.

Preserve two distinct phases in the proposed outcomes: the complete work is available only to localize the boundary, and only a content-free typed ceiling may leave that phase; evidence retrieval then stays at or before that ceiling.

Do not grade recorded system behavior, run Linger, create an adoption, or claim any proposal is adopted. Do not expose proposed Ground truth to the system under evaluation.

After writing both files, run the adopted validator against PACKAGE_DIRECTORY/backstory.json and PACKAGE_DIRECTORY/ground-truth.json. Fix only package-generation errors until deterministic validation succeeds. Validation covers schema, Backstory hashing, references, ordering, spans, evidence, pair differences, and resolved configuration facts; it does not judge semantic realism or label quality. Stop for independent human review.
```

## Ground truth lifecycle

The generator proposes candidate labels with exact Prop and Line spans, hash-bound repository evidence, safe-ceiling and forbidden-fact outcomes, retrieval decisions, and pairings. The adopted validator fails on schema or hash drift, unresolved references, bad ordering or spans, missing evidence files, source-hash mismatch, or false declared pair differences. It neither judges Linger output nor decides semantic correctness.

The existing independent local review workflow must present every complete Scene and proposal to a human who did not generate them. That reviewer adopts, revises, or rejects each label; `evals/synthetic_journals/adoption.py` binds complete adoption to exact bytes. Only adopted Ground truth may produce an adopted hard-gate grade, and neither proposed nor adopted Ground truth reaches Linger. Semantic realism, safe-ceiling correctness, forbidden-fact quality, and label quality remain review judgments, not deterministic checks. Review ownership, tooling, replay, and mixed-Objective grading are implemented.

## Architecture and academic relevance

Muse and Librarian participate, and Provenance is the mandatory independent release gate; the deterministic Memory & Policy Service supplies account-scoped Props. Sculptor and Serendipity do not participate. The plan tests a central authority boundary: complete-work access may localize a ceiling, but only a content-free candidate crosses into later bounded retrieval and release.

This produces a concrete testing artifact for agent coordination, explainability, traceability, unit and end-to-end verification—the briefing asks how agents coordinate and how those benefits can be demonstrated (Practice Module Briefing, p. 9), and lists testing artifacts among expected project outputs (p. 11).

> **Human decision required:** Approve the target design and runnable prompt, request revisions, or abandon this plan. Approval authorizes generation of the two proposed package files, not adoption or evaluation.
