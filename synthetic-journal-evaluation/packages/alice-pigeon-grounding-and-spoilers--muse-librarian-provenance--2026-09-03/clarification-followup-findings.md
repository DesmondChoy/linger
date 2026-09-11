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
| 10 | Repeated unsupported scene content and was rejected. | Asked for progress because the failed first turn was not stored. | Failed after upstream integration. |
| 11 | Released a reading check-in on first review. | Quoted the exact authorized paragraph on first review. | Both passed after upstream integration. |

The final prompt makes requests for actual wording explicit quotation requests.
It also tells Muse to remove an unsupported book claim completely during
revision. Replacing character names with pronouns does not resolve missing
evidence. No Provenance rule, chapter boundary, or failed-turn history rule was
relaxed to obtain the pass.

The upstream merge preserved the shared book registry, curated-memory access,
and explicit chapter-confirmation rules. The version 10 failure showed that
the check-in instruction still needed attention. Version 11 moves it to the
start of Muse's prompt and adds a generic example that contrasts responding
to a reader's pause with making a claim about a character. The example does
not mention Alice or the developer's test messages.

## Verified narrow result

The passing second turn used only
`pg11-v01b38ea4-ch05-ln0974-0975`. Both the route and search used exact passage
scope, with no completed-chapter ceiling. The answer included:

> “I can’t explain _myself_, I’m afraid, sir,” said Alice, “because I’m
> not myself, you see.”

The session retained two messages after turn one and four after turn two.
There were zero active memories throughout. The pre-merge first turn required
a revision; the final post-merge run needed none. One passing conversation
does not establish model reliability. The failed runs remain in the summary.

Final verification on Muse prompt version 11 passed 751 Python tests and 407
subtests. Five frontend tests, build, lint, book-registry validation, and Alice
corpus integrity also passed. The initial merged suite had three failures
because upstream tests still expected Muse-owned clarification delivery or a
safe decline. The updated tests require the application-owned question and
still reject an unsupported book answer. One new judge fixture also needed
the session-statements argument.

Commands used for local checks:

```sh
LOGFIRE_SEND_TO_LOGFIRE=false .venv/bin/python -m pytest -q
npm --prefix apps/frontend test
npm --prefix apps/frontend run build
npm --prefix apps/frontend run lint
.venv/bin/python -m src.linger.corpus.registry
.venv/bin/python -m src.linger.corpus.book src.linger.corpus.alice check
```

Pronoun-only follow-ups that cannot identify a book remain a separate tracked
gap, `linger-3yyi`.
