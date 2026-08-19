---
name: generate-synthetic-journals
description: Select Linger evaluation objectives, explain their scenarios and defaults, then generate a persona-neutral draft synthetic-journal dataset. Use when a developer asks to create, plan, or configure synthetic journal evaluation data; do not use for replaying an existing frozen dataset.
---

# Generate Synthetic Journals

Use `synthetic-journal-evaluation/evaluation-objectives.yaml` as the sole source
of evaluation-objective text, composition rules, workflow defaults, and prompt
boundaries. Never copy that content into this skill.

## Select objectives

1. Read the complete catalog and confirm that it contains exactly ten unique
   `evaluation_objectives`.
2. Initially surface only those ten objectives. Build labels and descriptions
   from each objective's `menu.title` and `menu.summary`; retain its `id` as the
   stable selection key. Do not surface workflow parameters yet.
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
   - Treat the harness-native **Skip** action or empty answer as no selection from
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
   titles. Reject an empty final selection, free-text response, and unknown or
   duplicate identifier. If a result contains **Other**, another free-text
   response, or both an objective and a mutually exclusive control sentinel,
   reject that group result and ask it again. Never convert free text into a new
   evaluation objective. Apply every rule under
   `selection_constraints`; in particular, injection resistance must accompany
   at least one legitimate primary objective.

If the harness exposes no native user-choice tool, stop and explain the missing
capability. Do not silently substitute a free-form prompt.

## Explain and confirm

After selection, explain each scenario using only its `menu` and `composition`
fields. Include relevant combination constraints. Then use the native choice
tool to ask whether the developer wants to:

- confirm and continue;
- revise the objective selection; or
- view all entries under `workflow_defaults`.

If defaults are requested, show every default's name, value, and description,
plus any applicable `conditional_developer_choices`. Defaults are informational:
ask the developer to choose only when a listed condition is true. Return to the
confirmation menu afterward. Do not start generation without confirmation.

## Generate the draft

After confirmation:

1. Read the selected objectives' `generation_brief` and `prompt_inputs`.
2. Resolve every prompt input through its declared supplier. Ask only the
   conditional developer questions that apply. Stop if an authoritative policy,
   corpus version, evidence record, or required workflow state cannot be resolved.
3. Give the generator only `generation_brief` and resolved prompt content. Keep
   `prompt_inputs`, `composition`, and `evaluation_metadata` out of generator
   context, as required by `prompt_boundary`.
4. Read `prompts/synthetic-journals/README.md` and use the active prompts plus
   `evals.synthetic_journals.generation` for profile, chunk, annotation, review,
   merge, and validation stages. Do not use archived prompts.
5. Keep raw journals separate from product memory, annotations grader-only, and
   the output in `draft` state. Generation does not authorize replay, freezing,
   committing, or publishing the dataset.

If the checked-in generation API cannot complete a canonical draft package,
report the exact missing stage and stop. Do not hand-assemble a partial package
or present it as generated data.
