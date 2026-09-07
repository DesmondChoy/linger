# Sculptor baseline evaluations

This directory owns the fixed baseline for Sculptor's post-capture memory
curation role. The owner identifier in every case is `sculptor`; Muse,
Provenance, and the Memory & Policy Service retain their separate capture,
review, and write responsibilities.

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

The synthetic-journal runner converts each isolated Scene's active,
same-account Props into `AccountScopedMemories` and calls production
`propose_curation`:

```bash
uv run python -m evals.synthetic_journals.curation_replay \
	path/to/backstory.json path/to/ground-truth.json \
	--adoption path/to/ground-truth-adoption.json \
	--output /tmp/bounded-memory-curation-run.json
```

The command records source hashes before and after every call, the complete
observable Sculptor exchange, typed output, hard-gate result, separate semantic
criteria, and correlated Logfire trace IDs. Proposal mode compares against
proposed Ground truth. Supplying a hash-valid `--adoption` grades the same hard
gates against independently adopted Ground truth; semantic quality remains a
separate review and cannot override a hard failure.

The artifact carries two identities. `full_deployment` covers the configured
model and every deployed prompt for lineage. `objective_execution` covers the
configured model, Sculptor prompt, and active curation contracts for behavioral
comparison. See
[`evals/synthetic_journals/README.md`](../synthetic_journals/README.md) for the
package topology, review command, and replay options.

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

The conversational `proactive_memory_surfacing` Objective requires reviewed
capture, curation application, later fresh-session memory use, and reviewed
response release. Offline component scores do not establish that complete
workflow.

## Versioning

The current case schema is version 1. Every case declares `schema_version: 1`
and uses a `-v1` case ID. Bump the schema version only for an incompatible
format change. Do not silently weaken or replace an accepted baseline case;
add a reviewed successor when its intended behaviour must change.
