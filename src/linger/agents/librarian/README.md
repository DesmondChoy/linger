# Librarian

Librarian owns one reusable PydanticAI object, `librarian_agent`, with two
application-selected skills. Each invocation is a model run with the selected
instructions and output contract. The assignment is explicit in
[`skills.py`](skills.py).

| Skill | Typed input and output | Entry point and current consumer |
|---|---|---|
| [Boundary inference](skills/boundary-inference/SKILL.md) | `LibrarianBoundaryInferenceInput` → `LibrarianBoundaryDecision` | `judge_spoiler_boundary` supports private inference during production book routing and book replay. |
| [Evidence assessment](skills/evidence-assessment/SKILL.md) | `LibrarianEvidenceStrengthInput` → `EvidenceStrengthDecision` | `judge_evidence_strength` selects evidence and assesses answerability after scoped retrieval. Production grounding and release evaluation use this path. |

Boundary inference receives the current Line, original reader statements,
projected account memories, and private full-work candidates. It distinguishes
memory-supported chapter progress from exact already-read passages supported
by earlier reader statements. Application code validates IDs, work identity,
confidence, and canonical scope before granting retrieval. Private candidates
do not enter Muse's context through this judgment.

Evidence assessment receives only a query and exact evidence already admitted
by retrieval policy. It chooses the smallest useful set and judges its
answerability independently of retrieval scores. Schema validation preserves
the sufficient, weak, and none requirements. Application code rejects invented
evidence IDs.

Both skills have no tools and retain one output retry. Shared instructions in
`agents.librarian` in the [`prompt catalogue`](../../prompts/prompt_catalog.yaml)
contain only common trust and authority rules. Each run adds its selected
`SKILL.md`; no run adds another task's instructions or conversation history.
Fingerprints cover both instruction layers and their contracts. Builders accept
injected models, and a production role override applies to either skill.

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
