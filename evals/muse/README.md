# Muse baseline evaluations

This directory owns the fixed baseline for Muse's conversational instruction
behaviours: responding to a personal reflection without demanding book
context, probing when a named book or chapter boundary needs confirmation,
grounding answers in retrieved evidence, and relaying a Serendipity decline
honestly. The owner identifier in every case is `muse`; Sculptor, Provenance,
and the Memory & Policy Service retain their separate responsibilities.

## Case contract

Each JSON file contains one reader message with its dynamic context and tool
transcript, one primary expected behaviour, probing and provenance invariants,
and explicit forbidden outcomes. `harness.py` requires exactly five cases and
one case for each baseline behaviour.

Hard grading is deterministic: a probe must ask a question, forbidden terms
must not appear as whole words, the reply must respect the word limit, and any
quotation-marked span of five or more words must be a substring of the
supplied librarian evidence, the reader's own message, or the decline's safe
next step. Fabricated text presented without quotation marks is beyond the
hard gates and belongs to the rubric. Free prose also carries a human or
secondary-LLM rubric. Semantic review is reported separately and can never
override a failed hard gate.

## Versioning

The current case schema is version 1. Every case declares `schema_version: 1`
and uses a `-v1` case ID. Bump the schema version only for an incompatible
format change. Do not silently weaken or replace an accepted baseline case;
add a reviewed successor when its intended behaviour must change.
