---
name: memory-curation
description: Propose one retrieval-oriented change to existing memories or leave them unchanged.
---

Propose one change that makes existing memories easier to retrieve, or leave
them unchanged. The JSON input contains `memories`, each with `memory_id` and
`text`, selected from one account. Return `curation_proposal` with one action,
or `no_curation_proposal` with a reason. Do not decide when to suggest a memory
to the reader.

Use `link_duplicates` only when every source expresses the same durable memory,
not merely similar words or a shared topic.

Use `update_derived_summary` when memories update, refine, or correct one
evolving fact. Cite only sources that contribute to that fact, and exclude
topical or contextual noise even when it shares words or a broad subject. The
summary must be supported by the cited sources together, with each source
contributing to the evolving fact. Preserve corrections, changes over time,
and unresolved uncertainty; do not present conflicting versions as
simultaneously true.

Use `assign_topic_group` when the memories are related by a useful theme but
each remains a separate, independently useful fact. Do not use a topic group to
avoid resolving updates to one evolving fact. When both actions seem plausible,
prefer `update_derived_summary` for one changing fact and
`assign_topic_group` for distinct facts. Prefer no change when the distinction
remains ambiguous.

Use `tombstone_for_retrieval` only for a record already linked to a distinct
canonical duplicate; it suppresses retrieval but never deletes the source. Use
`restore_to_retrieval` only to reverse such a tombstone. A tombstone proposal
must identify exactly the target and canonical memory. A restore proposal must
identify exactly its target.

Do not infer existing duplicate links or tombstone state from memory wording
or IDs. When the supplied input does not establish the required state, choose
another supported action or no change.
