---
name: memory-curation
description: Propose one retrieval-oriented change to existing memories or leave them unchanged.
---

Propose one change that makes existing memories easier to retrieve, or leave
them unchanged. The JSON input contains `memories`, each with `memory_id`,
`text`, and, when the application knows it, `recorded_at`: when the memory was
captured. That is when the note was written, not necessarily when the events
it describes happened. The memories are selected from one account. Return `curation_proposal` with one action,
or `no_curation_proposal` with a reason. Do not decide when to suggest a memory
to the reader.

The input may also contain `existing_curation`: the duplicate links,
retrieval tombstones, derived summaries, and topic groups the application has
already applied to these memories. It is application-owned state, not memory
text. When it is absent, no curation has been applied among these memories.
Build on it: propose the
next useful change, and never propose a link, summary, or group that it already
records. Return no change when nothing further would help.

Use `link_duplicates` only when every source expresses the same durable memory,
not merely similar words or a shared topic.

Use `update_derived_summary` when memories update, refine, or correct one
evolving fact. Cite only sources that contribute to that fact, and exclude
topical or contextual noise even when it shares words or a broad subject. The
summary must be supported by the cited sources together, with each source
contributing to the evolving fact. Preserve corrections, changes over time,
and unresolved uncertainty; do not present conflicting versions as
simultaneously true. When the text states when something happened or changed,
follow the text. Otherwise, order versions by `recorded_at` only when every
cited source has one and the times differ; a later note changes the fact only
when its text updates it. When capture times are missing, partial, or equal,
order versions only when their wording establishes the order, and otherwise
keep the conflict unresolved.

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

Read duplicate links and tombstone state only from `existing_curation`. Do
not infer them from memory wording or IDs. When `existing_curation` does not
establish the state an action requires, choose another supported action or no
change. When linked duplicates are all still retrievable, a tombstone for one
redundant record is a useful next change. Always keep one canonical record
retrievable.
