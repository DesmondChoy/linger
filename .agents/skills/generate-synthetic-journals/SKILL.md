---
name: generate-synthetic-journals
description: Select and confirm Linger evaluation objectives, inspect the current repository and academic requirements, then write a timestamped one-page Markdown pre-generation report for human review. Use when a developer wants to plan synthetic journal evaluation data without generating a dataset or invoking generation models.
---

# Generate Synthetic Journals

Use `synthetic-journal-evaluation/evaluation-objectives.yaml` as the sole source
of evaluation-objective text, composition rules, and prompt boundaries. Never
copy that content into this skill.

## Select objectives

1. Read the complete catalog and confirm that it contains exactly ten unique
   `evaluation_objectives`.
2. Initially surface only those ten objectives. Build labels and descriptions
   from each objective's `menu.title` and `menu.summary`; retain its `id` as the
   stable selection key.
3. Use the harness-native user-choice tool:
   - In Codex, call `request_user_input` when the harness exposes it.
   - In Claude Code, call `AskUserQuestion` with `multiSelect: true`.
   - In another harness, use its native multiple-choice or user-input tool.
4. Respect the tool's live schema. If one call cannot present ten multi-select
   options, paginate, group, or repeat native menu calls and combine the answers.
   A multi-select option list must contain evaluation objectives only. Never add
   **None**, **Skip**, **All**, **Finish**, **Other**, or another non-objective
   option to that list; native multi-select tools can allow it and an objective
   to be selected together.
   - Suppress harness-provided free-text choices when the live tool schema
     supports suppression. If the harness adds a free-text choice such as
     **Other** and provides no suppression setting, label the question with
     "Select only the listed evaluation objectives; free-text responses are not
     accepted." Treat that control as harness UI, not as an evaluation objective.
   - Treat the harness-native **Skip** control or empty answer as no selection from
     that group.
   - If the harness requires an answer and cannot return an empty group, first use
     a separate single-select question to choose **Select from this group** or
     **Skip this group**. Only after the first choice, show a multi-select question
     containing that group's objectives.
   For a single-select-only tool, let the developer add one objective per call,
   remove selected items from later calls, then ask **Add another** or **Finish
   selection** in a separate control question. Never truncate the catalog or
   replace the menu with an assumed choice.
5. Accept one through all ten objectives. Accept only exact catalog IDs or
   titles. Validate each group result before combining it. If a group contains
   **Other**, free text, an unknown value, or both an objective and a mutually
   exclusive control sentinel, discard only that group's complete result and
   ask the same group again. Never retain the valid-looking part of an invalid
   group or convert free text into a new evaluation objective.
6. After combining the group results, reject a candidate selection that is
   empty, contains a duplicate identifier, or violates any rule under
   `selection_constraints`; in particular, injection resistance must accompany
   at least one legitimate primary objective. Discard the complete candidate
   selection and restart from the full ten-objective catalog. Never silently
   deduplicate, remove, or otherwise repair an invalid candidate.

If the harness exposes no native user-choice tool, stop and explain the missing
capability. Do not silently substitute a free-form prompt.

## Explain and confirm

After selection, explain each scenario using only its `menu` and `composition`
fields. Include relevant combination constraints. Then use the native choice
tool to ask whether the developer wants to:

- confirm the objective selection;
- revise the objective selection.

If the developer chooses revision, discard the complete candidate selection and
restart from the full ten-objective catalog. Do not carry any prior choice
forward as selected. Confirmation does not start generation.

## Inspect the current project

Confirmation authorizes read-only analysis and one Markdown report; it does not
authorize synthetic-data generation. After confirmation:

1. Record the selected objective IDs and titles.
2. Snapshot the current repository with the branch, `HEAD` commit, dirty or clean
   status, local timestamp, and a concise fingerprint of the materially relevant
   files inspected. A report describes only that snapshot.
3. Read the selected objectives' complete catalog entries. Inspect the current
   implementation and focused tests for their declared agents, supporting
   components, mandatory gates, deterministic services, prompt inputs, and
   observable outcomes. Also inspect the five-agent architecture and shared
   authority boundaries in `docs/specification.md`; distinguish implemented,
   partial, missing, and merely proposed behavior. The report author and future
   generator both have read-only access to the current repository; never assume
   they need a frozen copy of repository content embedded in the prompt.
4. Read the complete academic source
   `docs/submissions/aas-practice-module-briefing.pdf`. Use its project questions
   and expected artifacts—especially multi-agent orchestration, explainability,
   responsible AI, AI security, modular design, testing, traceability, and
   MLSecOps/LLMSecOps—to assess why the selected scenarios matter. Do not invent
   a professor requirement or imply that a suggested opportunity is mandatory.
5. Decide whether each proposed Set should be corpus-backed or memory-only from
   the confirmed objectives and current implementation. Book use is optional
   unless an objective requires it. If book material is useful, point the future
   generator to the current `data/corpus/` directory and require it to discover
   the available work, immutable version, structure, and evidence there. Never
   hardcode a title, work ID, version, chapter, or evidence record in this skill
   or merely because it appeared in an earlier report. If book material is not
   useful, keep the Set memory-only and do not make corpus inspection busywork.
6. Draft the exact prompt proposed for a future generator. Build it from the
   selected objectives' `generation_brief`, the permitted repository paths, and
   concrete workflow inputs. State that the generator has read-only access to
   the current checkout and must inspect those paths at invocation time. Obey
   `prompt_boundary`: do not put `composition`,
   `evaluation_metadata`, ground truth, grading rules, component routes, or the
   report itself into the proposed generator prompt. The prompt may specify an
   output contract only when the project has adopted it. If a required input,
   schema, file layout, model setting, or other generation contract is unresolved,
   show a clearly marked unresolved slot in the prompt and mark the plan **not
   ready**; never invent repository state, evidence, or a file format.
7. For a book-backed spoiler scenario, prefer natural event-led context over a
   synthetic chapter-coordinate declaration. A Prop may describe events the
   person previously discussed, and a Line may refer to those events naturally.
   Use the complete current work as Librarian's boundary-inference search scope:
   it cross-references all chapters with the Prop and Line, then returns a typed
   candidate ceiling without returning later-story content to
   Muse. A second, bounded retrieval phase may return evidence only at or before
   that ceiling. Ground truth records the correct event-derived ceiling and
   grades Librarian's inferred ceiling, searched scope, returned evidence, and
   any clarification on low confidence. The current implementation instead
   requires a reader-confirmed chapter before dispatching Librarian, so report
   this two-phase inference contract as an implementation gap until it exists.
8. Hypothesize representative Line shapes, likely response behaviors, and how
   those behaviors could be evaluated. Treat response text as a hypothesis, not
   an exact oracle. Identify another Line or short Line sequence that still fits
   the confirmed objectives but is unsupported by the current implementation,
   and name the smallest plausible build-out needed. Label this as developer
   inspiration, not adopted scope.

## Write the pre-generation report

Create exactly one Markdown file under
`synthetic-journal-evaluation/reports/`, unless the caller supplies a different
output directory for an isolated test. Use the local timestamp in the sortable,
colon-free filename produced by
`%Y-%m-%dT%H%M%S%z-pre-generation-report.md`; if it already exists, insert
`-02`, `-03`, and so on immediately before `.md`.

The report is a one-page executive summary with a hard maximum of 700 words,
including headings and the proposed prompt. Keep it high-level, cite compact
repository paths and PDF page numbers, and include:

- the snapshot and selected scenarios;
- the corpus-backed or memory-only source decision and its reason;
- an explicit **ready** or **not ready** verdict with its decisive reason;
- the exact proposed generator prompt in a fenced block;
- representative Lines, response hypotheses, and evaluation approach;
- how the scenarios map onto the current architecture, all five agents, and
  deterministic services, including components expected not to participate;
- alignment with the professors' academic requirements; and
- one implementation-aware opportunity for additional Lines, plus material
  gaps, risks, or unresolved inputs.

End with **Human decision required: approve, revise, or abandon this plan.**
The report is only for the human or developer and must never be sent to a
generator. Do not invoke a generation model or create sets, props, scenes,
lines, ground truth, annotations, packages, manifests, frozen releases, or
replay data. After writing the report, verify its filename and word count,
report its path and selected objective IDs, then stop. The downstream generation
workflow remains intentionally undefined.
