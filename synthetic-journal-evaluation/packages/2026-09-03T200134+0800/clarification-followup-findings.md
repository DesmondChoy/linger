# Clarification and session-passage follow-up

## Scope

The developer requested two messages in one fresh conversation: a check-in about
reaching the Caterpillar scene, then a request for Alice's actual words about
not being herself. These targeted tests use `openai:gpt-5.6-luna`, with memory
capture disabled, no seeded personal memories, and remote telemetry disabled.
The [portable summary](clarification-followup-summary.json) contains the exact
inputs, released replies, retrieval scope, and artifact hashes for each run.

This is not a replay of the adopted synthetic Backstory. The earlier
[book evaluation findings](evaluation-findings.md), approved labels, and
two-of-four judgment result remain unchanged. The remembered-Prop selection
issue `linger-h4gl` is separate from this conversation-history failure.

## What failed

The clarification fix removes the requirement that Muse reproduce Librarian's
routing question word for word. After safety review, application code releases
the validated question. Muse still cannot attach evidence or call other tools
after that clarification. Search-result clarifications retain their existing
exact-wording contract.

That fix alone did not answer the two-message request. Muse had earlier reader
history, while private Librarian inference saw only the second message and no
saved memories. A located scene was therefore a `line_only` candidate, not
chapter permission. Exact session-supported paragraph grants fix that handoff
without pretending the reader completed the chapter.

Live tests then exposed two distinct response failures:

| Muse prompt | First message | Second message | Acceptance |
|---|---|---|---|
| 7 | Released after one revision. | Retrieved the correct paragraph but paraphrased it. | Failed: no requested quotation. |
| 8 | Retained an unsupported book interpretation after revision, so was declined. | Requested progress because the failed first turn was not stored. | Failed: no usable first turn. |
| 9 | Released a reading check-in after one revision. | Quoted the exact authorized paragraph with a first-pass review. | Both passed before upstream integration. |

The final prompt makes requests for actual wording explicit quotation requests.
It also tells Muse to remove an unsupported book claim completely during
revision. Replacing character names with pronouns does not resolve missing
evidence. No Provenance rule, chapter boundary, or failed-turn history rule was
relaxed to obtain the pass.

## Verified narrow result

The passing second turn used only
`pg11-v01b38ea4-ch05-ln0974-0975`. Both the route and search used exact passage
scope, with no completed-chapter ceiling. The answer included:

> “I can’t explain _myself_, I’m afraid, sir,” said Alice, “because I’m
> not myself, you see.”

The session retained two messages after turn one and four after turn two.
There were zero active memories throughout. The first turn still required a
revision, so the result demonstrates the complete release workflow, not
flawless first-draft behavior or guaranteed model reliability.

Local verification before these live runs passed 716 Python tests and 381
subtests, plus five frontend tests, build, and lint. The full suite is rerun
after the final prompt changes and upstream integration before publication.
Pronoun-only follow-ups that cannot identify a book remain a separate tracked
gap, `linger-3yyi`.
