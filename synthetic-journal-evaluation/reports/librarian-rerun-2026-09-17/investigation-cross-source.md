# Cross-source rerun investigation — 17 September 2026

Both remaining scenarios ran exactly once with `openai:gpt-5.6-luna`, after renewed authorization for OpenAI, Logfire and configured Exa access. Each exited 0. No production code, adopted inputs, grades or Beads were changed. No optional semantic judge or automatic rerun was invoked.

| Scenario | Scenes passing | Judgments passing | Interpretation |
| --- | ---: | ---: | --- |
| Roses, menu 6 | 1/3 | 1/4 | Retrieval worked; source declarations and final review failed. Two strict allowlist failures additionally reject a valid in-scope correction. |
| Alice/Hume, menu 8 | 3/3 | 4/4 | All three responses support their grades on direct semantic inspection. |

[Roses full Scene analysis](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-17T225605+0800-55d97da3.md>) and [Hume full Scene analysis](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/analysis-report-2026-09-17T230003+0800-6180364c.md>) cover every Scene, including passing controls. Original run details remain in [result-6.json](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/result-6.json>) and [result-8.json](</Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/reports/librarian-rerun-2026-09-17/result-8.json>).

## Roses S1: missing source declaration, plus strict expected-evidence mismatch

The positive comparison inspected and selected the exact personal note, the expected rose-painting passage, a second chapter-8 passage showing the Queen discovers the painting, and the adopted nursing study. Its final reply uses the note’s content (“you corrected the mistake, then said nothing”), but `evidence_uses` contains only the two book records and public URL. `missing_required_citation:S1C-memory` is a supported application failure. Internal declaration is required by [Muse reflection instructions](</Users/kevinmanuel/Documents/REPO/linger/src/linger/agents/muse/skills/reflection/SKILL.md:126>); this does not require visibly quoting the private note. Provenance passed this omission.

There is also a narrower claim-mapping defect: the declaration for `pg11-v01b38ea4-ch08-ln1931-1970` maps “The concealment fails” to the passage describing the gardeners’ intention. That outcome is instead supported by `pg11-v01b38ea4-ch08-ln2018-2074`, separately cited for the Queen’s discovery. The overall fact is true, but one individual declaration borrows support from a different record. This is not a retrieval hallucination.

The extra record produces `unpermitted_citation` and `unpermitted_selected_evidence`. An offline compiler probe found the adopted `S1C-book` accepts only `ch08-ln1962-1970`, `ch08-ln1931-1970`, and `ch08-ln1962-1990`. The later discovery record cannot match that span. The [grader](</Users/kevinmanuel/Documents/REPO/linger/evals/synthetic_journals/connection_replay.py:249>) enforces this exact expected-record allowlist, beyond production chapter permission. The Line explicitly completes chapter 8 and says “so she never finds out”; a factual correction is reasonably responsive to a literal outcome reading, even though the wording can also express the gardeners’ purpose. The correction is supported and within authorized chapter 8. These two failures therefore plausibly overstate a product error. They do not erase the independently supported missing-memory and claim-mapping defects.

Narrow next action: fix/verify declarations and claim-to-record mapping; separately review a successor expectation that can distinguish valid corrective support from gratuitous expansion. Do not widen reading scope or alter the adopted run to obtain green grades.

## Roses S2: invalid final review, correctly rejected by the application

The first Muse draft qualifies both sole-cause and universal claims and leaves a useful reflective question. Initial Provenance asks for the memory mapping to cover only the remembered event. Muse complies. In the revised candidate, `/1/supported_claims/0` is exactly:

> Your note records that you found and fixed the billing mistake, then said nothing.

The second model review nevertheless points to that path while quoting the event sentence plus the adjacent, **unmapped** sentence about the note leaving motives unresolved. The model therefore diagnoses an overbroad mapping that no longer exists. Its finding is itself incorrectly grounded in the current candidate.

An offline probe reconstructed `ProvenanceInput` and `ProvenanceReview` from saved S2 exchange 10 and called the production `validate_review`. It reproduced `ValueError: a finding quote does not match its declared source`. This is caught by the existing [finding validator](</Users/kevinmanuel/Documents/REPO/linger/src/linger/agents/provenance/models.py:323>), called in [reflection review](</Users/kevinmanuel/Documents/REPO/linger/src/linger/orchestration/reflection.py:775>). The [revision handler](</Users/kevinmanuel/Documents/REPO/linger/src/linger/orchestration/reflection.py:1233>) fails closed with `failure_stage=provenance_review` and `failure_type=validation`. The recorded release retains only the initial `revise`, not an accepted second verdict. The visible reply is a generic “Something went wrong…” request to ask again.

Both `missing_review_approval` failures are appropriate: [the grader](</Users/kevinmanuel/Documents/REPO/linger/evals/synthetic_journals/connection_replay.py:239>) requires an accepted final pass even for a safe decline. This was neither provider failure nor successful evidence-based restraint. The correct fix is better current-candidate review grounding and verification; preserve the validator. An invalid finding must not be treated as authorization to release.

## Hume: useful positive and negative controls

S1 retrieved the correct chapter-5 exchange and both other sources; all used sources have declarations. It quotes Alice accurately, attributes Hume’s view to philosophy, preserves the note’s stable timetable judgment, and offers a tentative question rather than a theory of the reader’s authentic self. The Hume claim about imagined identity across related succession is present in the opened snapshot before its truncated final sentence.

S2 explicitly rejects the stronger authenticity inference as unestablished. A revision maps the interpretation and frames its conclusion as a cautious reading of one note. Its final review validates successfully, with every prior finding resolved, and releases a useful qualified answer. A Serendipity `proposal` is allowed for restraint because the proposed comparison can remain useful while the stronger claim is declined; the [grader explicitly allows both proposal and decline](</Users/kevinmanuel/Documents/REPO/linger/evals/synthetic_journals/connection_replay.py:235>). Direct review confirms this is not a superficial pass.

Both S3 personal controls produced usable wording without search, unsolicited book facts, diagnosis or invented history. Hume’s final prompt is simply “Can I add something?” Roses offers optional language for the tension between honesty and self-protection.

## What this says about Librarian

Every book-dependent Scene in these two runs retrieved the requested chapter passage. The planner isolated the book reference, and the assessor selected supporting evidence. The roses failures occur in selection/declared source coverage and review, not from a missing requested book span. These observations cannot prove a global recall improvement, but they do not support attributing these failures to decomposition false negatives.

Roses S1 additionally shows a semantic choice worth testing: the assessor treated “so she never finds out” as an outcome requiring correction, then selected extra canonical evidence. Hume shows a complete reader question with personal/philosophical material can still yield a focused book request and a useful three-source response. In both Hume book Scenes, Muse also made a direct Librarian call before Serendipity performed its own book search; that duplicated work is visible but caused no correctness failure here.

## Verification and limits

Offline checks performed: recomputed all six source/adoption SHA-256 hashes against the saved menu/run result; all match. Compiled roses S1 to inspect its exact accepted book records. Validated every saved review against its actual input: roses S2 exchange 10 alone fails source-location validation; its initial review and all Hume reviews validate. These probes make no provider calls and do not change grades.

Both runs record only `get_page` query events for the exact granted public URL. [FrozenPageToolset](</Users/kevinmanuel/Documents/REPO/linger/evals/synthetic_journals/frozen_public_sources.py:27>) serves those pages from adopted local snapshots; no `web_search` event or private outward query was observed. This is a frozen-source replay, not a fresh web-content validation. Both SDK exports report `flushed: true`; remote trace visibility was not independently read back.
