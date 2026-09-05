# Synthetic book replay contract

## Decision

Book evaluation facts belong to the Scene they describe. Each book Objective
proposal contains only the judgment owned by that Objective, and validation
compiles the shared Scene facts and proposals into one replay plan.

The supported selections are `grounded_book_reflection`,
`spoiler_boundary_clarification`, or both. Selection order has no meaning.
Generic `grounding` remains exclusive to `weak_evidence_safe_decline`.

## Authoring shape

`ProposedGroundTruth.book_scene_facts` holds the shared book contract:

- the Scene ID;
- reader-confirmed, Librarian-inferred, or clarification scope;
- the Props and exact input spans that support inference or clarification;
- retrieval-neutral excerpts from the registered corpus.

Each book proposal uses one discriminated `book_expectation`:

- grounded reflection owns retrieval and exact-quotation policy;
- spoiler boundary owns the later evidence that must not be used or disclosed.

An inferred ceiling is derived from the supporting excerpts. Authors do not
repeat it. Work, version, chapter, path, hashes, and source lines are derived
from the registered corpus wherever possible, so contradictory copies cannot
be authored.

## Trusted boundary

Package validation is the only raw-data boundary. It validates package graph
coverage, Scene scope, exact source spans, the corpus catalog, and Objective
ownership. It then produces a closed replay plan used by both review and
execution.

Every adopted excerpt is compiled to the full set of production evidence
fingerprints that can contain it. A replay match requires the same work,
version, chapter, source hash, source lines, location, and window text. Equal
text from another chapter or corpus version does not match.

## Runtime observation

Librarian inspection retains the tool name for each released route or search
call. Production and evaluation share one route reducer:

1. The first clarification anywhere in the ordered route calls is binding.
2. Otherwise, the first routed work supplies the scope.
3. Only `no_match` results produce `no_match`.
4. No route call produces an absent route.

Reader-confirmed scope comes from trusted session context. Inferred and
clarification scope comes from `librarian_route`. Evaluation-only boundary
support may explain a decision, but it never becomes release authority.

## Grading and adoption

The book runner grades every selected book proposal. It does not assume one
Prop, three Scenes, or a fixed Objective order. It rejects a no-retrieval
grounded expectation when another proposal in the same Scene requires routing.

Deterministic hard gates cover route outcome, safe scope, exact evidence flow,
exact quotation, exact forbidden text, Provenance, and unexpected capture.
Semantic paraphrase review is optional, labeled non-independent, keyed by Scene
and proposal, and reported separately from the deterministic hard pass.

Adoption remains one human decision per proposal and stays bound to the exact
proposed Ground truth file hash. Changing shared Scene facts invalidates the
entire adoption. Old book packages and their approvals are not translated or
reused.

## Rejected alternatives

A repository-wide proposal-schema rewrite would make every Objective use a
discriminated union, but it would migrate unrelated capture, curation, and
continuity paths. Keeping the existing book fields and reconciling them in a
validator would leave duplicate authorities in the wire format. Letting one
proposal own shared scope would make ownership depend on which Objectives a
package selects. The Scene-owned book record avoids all three problems while
limiting the breaking change to book evaluation.
