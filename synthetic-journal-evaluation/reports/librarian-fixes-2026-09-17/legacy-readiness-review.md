# Legacy scenario readiness

This read-only source audit covers saved-menu entries 1, 2, 3 and 5. Proposed files are confined to `expectation-proposals/`; original scenario files and adoption records are unchanged. No provider calls or adoption records were created.

| Menu | Scenario | Result | Human decision needed |
| --- | --- | --- | --- |
| 1 | Alice Caterpillar grounding and spoilers | A schema-only proposed successor validates: 3 Scenes, 4 proposals. | Review the preserved inference expectation against the current requirement that a quoted scene mention alone does not prove reading progress; then independently adopt or revise the successor. |
| 2 | Alice identity connections and restraint | Existing originals validate: 3 Scenes, 4 proposals. No copy is needed. | Independently review/adopt the unchanged proposal; no adoption file exists. |
| 3 | Alice kitchen spoiler boundary | Existing schema is stale; completing current typed facts requires semantic evidence choices. No successor was invented. | Select canonical forbidden-event witnesses and resolve whether the prohibited Hatter reference means the later tea-party scene or the name already present in permitted chapter 6. |
| 5 | Alice quotation grounding | Existing schema is stale; the original `chapter_max=5` does not identify how permission is established. No successor was invented. | Decide whether to add an explicit completed-chapter statement, endorse a specified memory-supported inference, or redesign around narrow session-supported passage permission. |

## Menu 1: concrete schema successor

Files: [backstory.json](expectation-proposals/menu-1-caterpillar-schema-successor/backstory.json), [ground-truth.json](expectation-proposals/menu-1-caterpillar-schema-successor/ground-truth.json), [migration record](expectation-proposals/menu-1-caterpillar-schema-successor/migration.json).

The Backstory is byte-identical to the original. The migration moves the original inferred/clarification scope, authorized Prop IDs, basis spans and corpus evidence into `book_scene_facts`. It converts the old per-objective fields into `book_expectation`, derives registered chapter IDs from the unchanged corpus metadata, and removes duplicated old ownership fields. Expected/prohibited prose, all Lines, Prop text, excerpt text and offsets remain unchanged. The old explicit chapter-5 ceiling is now derived from its original chapter-5 support, as the current contract requires.

Every original repository evidence hash and span matched the current immutable corpus. Current validation returned `SCENARIO_VALIDATION_OK=3 scenes,4 proposals`. The old adoption cannot cover the changed Ground truth bytes. This is a proposed successor, not approved labels or a passing evaluation.

One semantic question remains despite successful structural validation: the current Line asks for a Caterpillar quote, and the Prop says Alice changed size and became uncertain about identity; neither explicitly says the reader stopped or completed chapter 5. The original expectation directly requires inference to chapter 5. The migration preserves that requirement rather than deciding whether the current application should treat these signals as sufficient. A human must retain, revise or reject that expectation; do not silently insert a new reading claim to force a pass.

## Menu 2: ready for independent review

Use the existing files in `synthetic-journal-evaluation/scenarios/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/`. Current validation passes unchanged, including the declared exact repository spans. Backstory SHA-256 remains `34e900f0d1326a66e473536f336e5797335d829093f1180bf21b3ec1fb7fcada`; proposed Ground truth remains `0cc016b37cf226bb51fe93b1760128d80b52f85de366e56e686cf64c377fa6b5`.

The only recorded readiness blocker is missing independent adoption. Validation establishes schema and source consistency, not the quality of the Alice/Hume comparison or semantic correctness of each label. Those remain review decisions. No duplicate candidate files were written.

## Menu 3: exact missing choices

Original files are in `synthetic-journal-evaluation/scenarios/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/`. Both proposals lack current `book_expectation` and shared `book_scene_facts`. The positive proposal has exact chapter-6 pepper, pig and directions excerpts; all hashes and spans resolve, although the authored excerpts deliberately end mid-sentence. The negative proposal has no canonical evidence. Both store forbidden facts only as prose in legacy `grounding.forbidden_post_boundary_facts`.

The current spoiler contract requires at least one `forbidden_later_evidence_id` backed by a specific canonical occurrence for each Scene. Converting the prose into such occurrences requires selecting and independently reviewing new source spans, not simply renaming fields. The authorized Prop IDs and full Prop/Line basis can be transcribed, but which chapter-6 passages jointly establish the exact stopped event also needs explicit support labeling.

There is a concrete scope conflict to resolve: the positive prohibited prose can be read as forbidding any mention of the Hatter, while its permitted Cat-directions excerpt already names the Hatter and March Hare in chapter 6. Decide whether only their later tea-table events are forbidden. Also decide whether to preserve the original three permitted chapter-6 windows or broaden them enough to include complete statements. Do not remove forbidden material checks merely to make this Scenario validate.

## Menu 5: exact missing permission choice

Original files are in `synthetic-journal-evaluation/scenarios/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/`. The chapter-5 quotation resolves exactly. The old `grounding.expected.chapter_max=5` constrains retrieval but does not say whether the reader confirmed that ceiling or whether it was inferred. The Prop reports reaching the Caterpillar, stopping briefly and a reading pace; the current Line requests wording, not chapter completion. The Backstory is evaluation-only and cannot independently grant runtime permission.

The typed successor needs a `BookSceneFacts.scope` choice. `reader_confirmed` would require a new explicit reading statement. `librarian_inferred` needs approved Prop/Line basis spans and canonical support labels; choosing it is a new explicit authority expectation. Narrow passage permission would require earlier original session reader statements and a suitable replay topology, which this fresh-session single-Line Scenario does not provide. Preserve the personal no-retrieval control under any chosen successor; do not turn its shared reading Prop into an unsolicited book answer.

These are concrete review choices, not requests to change the corpus. Once chosen, create and validate the full successor, then obtain fresh independent adoption before evaluation.
