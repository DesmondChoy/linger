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
2. Resolve `scripts/objective_selector.py` relative to this `SKILL.md` and run it
   with the repository's Python environment as a long-running local process.
   Surface the printed `OBJECTIVE_SELECTOR_URL` as a clickable link and wait for
   the process to finish. Do not use a harness-native choice tool or accept a
   conversational objective selection. If the first launch exits with status 3
   and prints `OBJECTIVE_SELECTOR_BIND_PERMISSION_REQUIRED=127.0.0.1`, retry the
   exact command once through the harness's narrow approval or elevation
   mechanism for local binding. This is permission recovery, not a terminal
   selector failure. Keep the approved retry bound to `127.0.0.1`; never use a
   non-loopback host, disable the sandbox, or ask the developer to change global
   security settings.
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

## Inspect the current project

Confirmation authorizes read-only analysis and one Markdown report; it does not
authorize synthetic-data generation. After confirmation:

1. Record the selected objective IDs and titles.
2. Snapshot the current repository with the branch, `HEAD` commit, dirty or clean
   status, local timestamp, and a concise fingerprint of the materially relevant
   files inspected. A report describes only that snapshot. If the working tree is
   dirty, identify the materially relevant changes and explain that the report
   cannot be reproduced from `HEAD` alone.
3. Read the selected objectives' complete catalog entries. Inspect the current
   implementation and focused tests for their declared agents, supporting
   components, mandatory gates, deterministic services, prompt inputs, and
   observable outcomes. Also inspect the five-agent architecture and shared
   authority boundaries in `docs/specification.md`; distinguish implemented,
   partial, missing, and merely proposed behavior. Read Section 7.2.1 completely
   and use its six canonical nouns exactly: `Objective`, `Backstory`, `Prop`,
   `Scene`, `Line`, and `Ground truth`. Use implementation terms such as `batch`
   only for the actual runtime object, never as a replacement for `Scene`. The report
   author and future generator both have read-only access to the current
   repository; never assume they need a frozen copy of repository content
   embedded in the prompt.
4. Read the complete academic source
   `docs/submissions/aas-practice-module-briefing.pdf`. Use its project questions
   and expected artifacts—especially multi-agent orchestration, explainability,
   responsible AI, AI security, modular design, testing, traceability, and
   MLSecOps/LLMSecOps—to assess why the selected scenarios matter. Do not invent
   a professor requirement or imply that a suggested opportunity is mandatory.
5. Decide whether the proposed Backstory should be corpus-backed or memory-only
   from the confirmed objectives and current implementation. Book use is
   optional unless an objective requires it. If book material is useful, point the future
   generator to the current `data/corpus/` directory and require it to discover
   the available work, immutable version, structure, and evidence there. Never
   hardcode a title, work ID, version, chapter, or evidence record in this skill
   or merely because it appeared in an earlier report. If book material is not
   useful, keep the Backstory memory-only and do not make corpus inspection
   busywork.
6. Draft the exact prompt proposed for a future generator. Build it from the
   selected objectives' `generation_brief`, the permitted repository paths, and
   concrete workflow inputs. State that the generator has read-only access to
   the current checkout and must inspect those paths at invocation time. Obey
   `prompt_boundary`: do not put `composition`,
   `evaluation_metadata`, ground truth, grading rules, component routes, or the
   report itself into the proposed generator prompt. Do not add canonical nouns
   merely because the human report must account for them. Use a canonical noun
   in the generator prompt only when the permitted generation brief, a resolved
   workflow input, or an adopted output contract requires it. The prompt may
   specify an output contract only when the project has adopted it. If a required
   input, schema, file layout, model setting, or other generation contract is
   unresolved, show a clearly marked unresolved slot in the prompt and mark the
   plan **not ready**; never invent repository state, evidence, or a file format.
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
8. Hypothesize representative inputs, likely response behaviors, and how those
   behaviors could be evaluated. Use the canonical term `Line` only for
   conversational input sent to Muse. Describe offline curation inputs by their
   actual roles. Keep every plan to one Backstory representing one person and one
   evaluation account. Every Prop, Scene, and Line must belong to that Backstory;
   identify each Prop's planned lifecycle role. Do not treat a Backstory as a
   runtime actor. Treat response text as a hypothesis, not an exact oracle.
   Identify another input or short input sequence that still fits the confirmed
   objectives but is unsupported by the current implementation, and name the
   smallest plausible build-out needed. Label this as developer inspiration,
   not adopted scope.

## Write the pre-generation report

Create exactly one Markdown file under
`synthetic-journal-evaluation/reports/`, unless the caller supplies a different
output directory for an isolated test. Use the local timestamp in the sortable,
colon-free filename produced by
`%Y-%m-%dT%H%M%S%z-pre-generation-report.md`; if it already exists, insert
`-02`, `-03`, and so on immediately before `.md`.

Before drafting the report, invoke `$google-developer-docs-style` when that
skill is available and follow it. If the skill is unavailable, search the web
for the current official Google developer documentation style guide, read the
relevant pages under `developers.google.com/style/`, and apply that guidance.

The report is a one-page decision memo with a hard maximum of 700 words,
including headings and the proposed prompt. Write for the developer deciding
whether to proceed. Use direct, conversational language, active voice,
sentence-case headings, short paragraphs, and compact repository paths and PDF
page citations. Prefer narrow bulleted lists and blockquote callouts over dense
paragraphs or tables, except for the required compact canonical-noun table.
Introduce each list with a complete sentence, keep list items parallel, and
define necessary project terms on first use.

Use the following sections in this order:

1. **Decision.** Put a blockquote callout immediately after the title. State
   **ready** or **not ready**, the decisive reason, and the practical consequence.
   If the plan is not ready, recommend the smallest decision or repository
   change that would unblock generation. Do not merely restate the unresolved
   input or fold later Ground truth assignment into the generator's output
   contract.
2. **Your selection.** Summarize what the developer selected before presenting
   the plan. Use one short bullet per selected Objective with its human-readable
   title, ID, and a plain-language summary derived only from its catalog
   `menu.summary`. Do not merely repeat IDs or add interpretation.
3. **Selected plan.** Cite and link `docs/specification.md` Section 7.2.1 at the
   first canonical-noun reference, using a path that resolves from the report's
   output directory. Follow the citation with a compact two-column Markdown
   table whose body contains exactly six rows in this order: `Objective`,
   `Backstory`, `Prop`, `Scene`, `Line`, and `Ground truth`. The second column
   must explain how the selected plan uses each noun or why it does not apply. Use the Objectives'
   human-readable titles and IDs; explain why they form one coherent plan; state
   whether the single Backstory is corpus-backed or memory-only; distinguish
   pre-Scene Props from records created as runtime outcomes; derive minimum
   Scene counts only from the catalog; state whether any Lines exist; and distinguish evaluation
   hypotheses from Ground truth assigned after generation and withheld from the
   generator. Do not invent counts, schemas, or file layouts.
4. **Expected behavior and evaluation.** Start by stating whether the selected
   plan contains conversational Lines. If it does, label each representative
   Line explicitly. If it does not, name the actual input types, such as offline
   curation Props. For each Scene or
   coherent ordered Scene sequence, use bullets to pair a representative input
   with the likely behavior and a plain-language success check. Put metric names
   after the explanation, if they add value. Treat response text as a hypothesis,
   not an exact oracle.
5. **Proposed generator prompt.** Include the exact proposed prompt in a fenced
   code block. Make every unresolved slot visually clear and connect it to the
   decision callout. Do not insert `Objective`, `Backstory`, `Prop`, `Scene`,
   `Line`, or `Ground truth` merely for vocabulary coverage. Include a canonical
   noun only when an adopted output contract requires it and `prompt_boundary`
   permits it; never include Ground truth.
6. **Architecture and academic relevance.** Use bullets to identify participating
   agents, non-participating agents, and deterministic services. Explain why
   non-participation matters when it tests an authority boundary. Make one
   concrete claim about how the plan supports the professors' academic
   requirements, with the relevant PDF page citation. Avoid generic alignment
   language.
7. **Risks and opportunity.** Separate blocking gaps from non-blocking risks.
   Name the generated canonical entities affected by an unresolved output
   contract. Report Ground truth assignment as a separate downstream decision;
   never imply that Ground truth belongs in the generator's output contract.
   Include one implementation-aware opportunity for an additional input and the
   smallest plausible build-out. Label it as developer inspiration, not adopted
   scope.
8. **Provenance.** Put the snapshot last. Keep it compact: timestamp, branch,
   `HEAD`, dirty or clean status, materially relevant dirty changes, inspected
   paths, and their concise fingerprint. If the tree is dirty, state that `HEAD`
   alone cannot reproduce the report.

End with a **Human decision required** callout whose options match the verdict.
For a ready plan, offer approve, revise, or abandon. For a not-ready plan, offer
the recommended unblock, revise, or abandon; do not offer approval of the plan
unchanged.

The report is only for the human or developer and must never be sent to a
generator. Do not invoke a generation model or create backstories, props, scenes,
lines, ground truth, annotations, packages, manifests, frozen releases, or
replay data. After writing the report, verify its filename and word count. Also
verify that the canonical-noun table has the exact six rows and a working
Section 7.2.1 link; runtime-created outcomes are not called Props; hypotheses
are not called Ground truth; the report uses exactly one Backstory, person, and
evaluation account; every Prop, Scene, and Line belongs to that Backstory; every
Prop identifies its planned lifecycle role; and report-only vocabulary has not
leaked into the generator prompt. Report the path and selected Objective IDs, then stop. The
downstream generation workflow remains intentionally undefined.
