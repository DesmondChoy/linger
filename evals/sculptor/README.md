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

## Versioning

The current case schema is version 1. Every case declares `schema_version: 1`
and uses a `-v1` case ID. Bump the schema version only for an incompatible
format change. Do not silently weaken or replace an accepted baseline case;
add a reviewed successor when its intended behaviour must change.
