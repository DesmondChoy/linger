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
Each planned part gets its own search. Uncertain parts remain eligible, and
original reader text supplies a fallback search within the same authorized
scope. Candidate streams are interleaved so an early part cannot consume the
entire private evidence pool. Answer retrieval allows at most 16 queries of
2,000 characters, with at most 20 combined candidates. A larger request fails
explicitly rather than dropping requirements. The final evidence limit remains
separate from these private search budgets.

Evidence assessment receives both the plan and original reader context. It can
recover omitted needs in `additional_parts`, whose spans must also match the
original text. Sufficient evidence must cover every planned and recovered part.
Useful but incomplete evidence retains explicit limitations. The application
rejects unknown support indices, invented evidence IDs, and excess selections.
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

All four skills have no tools and retain one output retry, with an explicit
request budget sized to that retry so a model answering with calls to tools it
was never given fails to the caller's existing fallback rather than looping on
retry prompts. Shared instructions in
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

See the [runtime architecture](../../../../docs/agent-skills.md),
[Librarian subsystem design](../../../../docs/design/librarian-design.md), and
[retrieval evaluation](../../../../evals/librarian/README.md) for scope and
evidence boundaries.
