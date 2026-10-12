# Librarian

Librarian owns one reusable PydanticAI object, `librarian_agent`, with four
application-selected skills. Each invocation is a model run with the selected
instructions and output contract. The assignment is explicit in
[`skills.py`](skills.py).

| Skill | Typed input and output | Entry point and current consumer |
|---|---|---|
| [Boundary inference](skills/boundary-inference/SKILL.md) | `LibrarianBoundaryInferenceInput` → `LibrarianBoundaryDecision` | `judge_spoiler_boundary` supports private inference during production book routing and book replay. |
| [Event identification](skills/event-identification/SKILL.md) | `LibrarianEventIdentificationInput` → `LibrarianEventIdentification` | `identify_reader_event` independently checks the stopping event before application code accepts a chapter candidate. |
| [Book request](skills/book-request/SKILL.md) | `LibrarianBookRequestInput` → `BookRequestPlan` | `plan_book_request` extracts separate book needs or reading-progress locators, selected by the application. |
| [Evidence assessment](skills/evidence-assessment/SKILL.md) | `LibrarianEvidenceStrengthInput` → `BookEvidenceAssessment` | `assess_book_evidence` checks scoped records against the plan and original reader context. Application checks return `EvidenceStrengthDecision`. |

Boundary inference receives the current Line, original reader statements,
projected account memories, and private full-work candidates. It distinguishes
memory-supported chapter progress from exact already-read passages supported
by earlier reader statements. Application code validates IDs, work identity,
confidence, and canonical scope before granting retrieval. Private candidates
do not enter Muse's context through this judgment.

A chapter candidate accounts for every supplied passage in `event_resolution`,
selects one occurrence using exact reader wording, and binds each supporting
record to a literal `source_excerpt`. The application validates that inventory
and the memory assessments. A separate event-identification run then receives
only the original reader wording and canonical candidates. It sees neither the
proposed grant nor the memories. The identified stopping occurrence must agree
with the candidate's chapter and source range. Unresolved identification,
disagreement, or failure grants no chapter access. Exact-passage decisions use
their separate reader-statement checks.

Book-request planning receives reader context without candidate passages.
Application code validates exact reader spans and the selected search target.
Each named event or book need gets its own search, including each event in a
sequence. Uncertain parts remain eligible. Original reader text supplies
fallback searches within the same authorized scope.

Answer retrieval allows at most 16 distinct queries of 2,000 characters. A
larger request fails explicitly. Every query searches each granted book, then
part routing retains four candidates in a clearly matching book or four per
book when the match is ambiguous. Each whole-context fallback retains two per
book, or twenty when no plan is available. Interleaving and removal of fully
contained windows produce a pool of at most twenty records per book. Partially
overlapping windows remain because their unique lines can contain the answer.
The caller selects at most five final records across the search.

Evidence assessment receives both the plan and original reader context. It can
recover omitted needs in `additional_parts`, whose spans must also match the
original text. Sufficient evidence must cover every planned and recovered part.
Useful but incomplete evidence retains explicit limitations. The application
returns invalid spans, missing part coverage, unknown support indices,
invented evidence IDs, and excess selections to the model's repair loop.
Application code rejects any invalid result that remains after the retry.
Planning failures are recorded and use original-text retrieval as a fallback.
An empty authorized plan also gets that recovery path; no authorized scope
means no search. Exact-passage grants still assess only the granted records.

Progress search uses focused event locators plus the original progress query,
then interleaves those candidates with memory searches under a private
20-record boundary budget. The boundary judge receives the original reader
and memory text. Planning never grants progress or resolves an ambiguous event.
One planning model run precedes boundary retrieval, and each request can
perform several local searches.

Omission remains a model-quality risk: both planning and assessment can overlook
a need. Exact-span checks prevent invented wording, not semantic omissions.
The recall fallback and coverage check reduce that risk without claiming to
eliminate it. Reranking splits oversized query/passage pairs into overlapping
token windows and retains the highest score for each unchanged canonical record.
This prevents silent token truncation; it does not prove semantic relevance or
authorize a reading boundary. Incorrect semantic boundary grants still require
separate validation; a high retrieval score does not establish safety.
An irrelevant passage can also score highly, so evidence assessment must check
what it actually supports instead of relying on the score to reject it.

All four skills have no tools and retain one output retry. Shared instructions in
`agents.librarian` in the [`prompt catalogue`](../../prompts/prompt_catalog.yaml)
contain only common trust and authority rules. Each run adds its selected
`SKILL.md`; no run adds another task's instructions or conversation history.
Fingerprints cover both instruction layers and their contracts. Builders accept
injected models, and a production role override applies to every skill.

The Librarian subsystem also resolves work identity, searches, filters, fuses,
deduplicates, reranks, and resolves canonical records. These deterministic
operations remain application services. They are not extra model skills.
The runtime registry and default access list include Alice, Animal Farm,
Pinocchio, Frederick Douglass's Narrative, and The Story of My Life. Preparing
a new corpus still requires separate registration before conversation use.
The checked-in retrieval benchmark and live release report cover Alice only.

`HybridLibrarian(read_chapter_cues=True)` includes each chapter's reviewed
description, characters, and retrieval cues in keyword, semantic, and reranker
search text. Canonical passage text and evidence identity remain unchanged.
Chapter cues default to off. The offline retrieval experiments can also pass
`part_candidates=20` to candidate gathering; production uses four. The
[retrieval evaluation guide](../../../../evals/librarian/README.md#chapter-cue-and-retrieval-research-experiments)
documents frozen plans, owner approvals, practice traces, and the distinction
between a passage reaching the pool and being selected as evidence.

See the [runtime architecture](../../../../docs/agent-skills.md),
[Librarian subsystem design](../../../../docs/design/librarian-design.md), and
[retrieval evaluation](../../../../evals/librarian/README.md) for scope and
evidence boundaries.
