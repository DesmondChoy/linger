---
name: memory-curation
description: Propose one retrieval-oriented change to existing memories or leave them unchanged.
---

Use this task to propose retrieval-oriented curation of existing memories.
The application supplies a bounded set of memory IDs and text from one account.
Propose exactly one action, or explicitly propose no change. This task does not
decide when a memory should be surfaced to the reader.

Use `link_duplicates` only when every source expresses the same durable memory,
not merely similar words or a shared topic.

Use `update_derived_summary` when memories update, refine, or correct one
evolving fact. Cite only sources that contribute to that fact, and exclude
topical or contextual noise even when it shares words or a broad subject. The
summary must be supported by every cited source and must preserve uncertainty.

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
