# Sculptor baseline evaluations

This directory owns the fixed baseline for Sculptor's post-capture memory
curation role. The owner identifier in every case is `sculptor`; Muse,
Provenance, and the Memory & Policy Service retain their separate capture,
review, and write responsibilities.

One reusable `sculptor_agent` runs five application-selected skills:
[memory curation](../../src/linger/agents/sculptor/skills/memory-curation/SKILL.md),
[memory surfacing](../../src/linger/agents/sculptor/skills/memory-surfacing/SKILL.md),
[chapter cues](../../src/linger/agents/sculptor/skills/chapter-cues/SKILL.md),
[retrieval error analysis](../../src/linger/agents/sculptor/skills/retrieval-error-analysis/SKILL.md),
and [retrieval research](../../src/linger/agents/sculptor/skills/retrieval-research/SKILL.md).
Each entry point selects its typed output schema and retains independent
role-and-task tracing. A role model override applies to all five tasks. Evaluation
skill IDs and fingerprints distinguish their contracts and effective shared
and task instructions, even though they share the Agent object.

## Case contract

Each JSON file contains one bounded account-scoped memory set, one primary
expected behaviour, immutable-original and provenance requirements, and
explicit forbidden outcomes. `harness.py` requires exactly five cases and one
case for each baseline behaviour.

Hard grading is deterministic: response kind, action, source-memory IDs,
schema, provenance boundaries, and summary length. Generated summary text and
topic labels also carry a human or secondary-LLM rubric. Semantic review is
reported separately and can never override a failed hard gate.

Run the case-contract and hard-gate tests from the repository root:

```bash
uv run pytest tests/test_sculptor_evals.py
```

## Provider-backed bounded-curation replay

The standalone synthetic scenario runner resolves each isolated Scene's active,
same-account Props and calls production `run_curation_loop`. Sculptor sees each
source's capture time when supplied and the curation already applied to the
selected memories. It proposes an action, Provenance reviews the exact bound
proposal, and the Memory & Policy Service applies an allowed action and
verifies its audit record:

```bash
uv run python -m evals.synthetic_journals.curation_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/bounded-memory-curation-run.json
```

The command records source hashes before and after every call, the complete
observable Sculptor and Provenance exchanges, typed output, curation-loop
status, hard-gate result, separate semantic criteria, and correlated Logfire
trace IDs. Hard gates include the expected review decision, application, audit,
and source preservation. Proposal mode compares against
proposed Ground truth. Supplying a hash-valid `--adoption` grades the same hard
gates against independently adopted Ground truth; semantic quality remains a
separate review and cannot override a hard failure.

The artifact carries two identities. `full_deployment` covers the configured
model and every deployed prompt for lineage. `objective_execution` covers the
configured model, Sculptor prompt, and active curation contracts for behavioral
comparison. See
[`evals/synthetic_journals/README.md`](../synthetic_journals/README.md) for the
scenario topology, review command, and replay options.

The [combined capture and curation runner](../synthetic_journals/README.md#combined-capture-and-curation-replay)
uses production Sculptor and production Provenance. Curation receives
designated Props in isolated storage; captured records do not become curation
inputs. That runner grades the reviewed curation loop but does not exercise
chat's capture-triggered batch selection.

The [memory curation and recall loop](../synthetic_journals/README.md#memory-curation-and-recall-loop-replay)
measures recall before curation and after one, two, and three cumulative rounds.
Every repetition starts with the same isolated Prop bank. Sculptor receives
existing curation state and capture times without reader Lines or relevance
labels. This experiment measures retrieval outcomes separately from proposal
quality, review decisions, and immutable-source checks.

## Offline memory-surfacing decisions

`surfacing_harness.py` grades the separate Sculptor decision contract for
`surface_now`, `defer`, and `do_not_surface`. Its cases cover timely, deferred,
superseded, repeated, unsupported, and sensitive situations. Hard gates check
source selection, decision, refusal reason, and deferral kind and time.
Suggestion quality and the meaning of a deferral condition require independent
review.

The provider-backed
[offline surfacing replay](../synthetic_journals/README.md#offline-memory-surfacing-component-replay)
supplies bounded synthetic memories, current context, decision time, and prior
surfacing history to the tool-free agent. It records source preservation,
decision metrics, hard failures, and complete agent exchanges. The command
grants no retrieval, memory writes, conversational release, scheduling, or
notification authority.

Memory surfacing is offline only. Chat never runs it, so these scores measure
Sculptor's decisions, not a conversational reply.

## Offline retrieval improvement

The [Librarian evaluation guide](../librarian/README.md#chapter-cue-and-retrieval-research-experiments)
documents three further Sculptor tasks and their commands. The chapter-cues task revises
every chapter's metadata within a word budget, using practice search outcomes.
Error analysis reads practice traces and names counted failure categories.
Retrieval research uses the approved analysis and bounded Exa searches to
propose a specification for a developer.

These experiments require owner approval of exact proposals before later
stages consume them. They keep every attempt, freeze request plans, and measure
candidate recall separately from Librarian's selected evidence. Held-back
needs do not enter Sculptor's inputs. Research proposals do not edit code,
change the production retriever, or establish an end-to-end release result.

## Versioning

The current case schema is version 1. Every case declares `schema_version: 1`
and uses a `-v1` case ID. Bump the schema version only for an incompatible
format change. Do not silently weaken or replace an accepted baseline case;
add a reviewed successor when its intended behaviour must change.
