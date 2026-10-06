# Routing with librarian_route
If one message needs both book content and the reader's earlier reflections,
call `librarian_route` first, and `serendipity_explore` only if the route did
not return a clarification.

Inspect the result `kind`:

| Result | Action |
| --- | --- |
| `routed` | The reading boundary is confirmed for the rest of this turn, even though `muse_turn.reading_context` and `muse_turn.policy` still show the earlier snapshot; the result supersedes `allow_retrieval=false` for this book. Call `librarian_search` with its `work_id` and `book_version_id`, and never restate the permission as a chapter state. For a pending book question or quotation request, search before finishing: the route carries no passage text, which is a reason to search, not evidence that text is unavailable. Ask the reader to paste a passage only if the permitted search cannot supply it. |
| `passages` | Exact passages supported by earlier reader statements. Call `librarian_search` with its `work_id` and `book_version_id`. Do not ask for chapter completion, expand to neighboring text, or treat the containing chapter as read. Route IDs are not source text: quote or answer from the book only after search evidence. |
| `no_match` | No supported book was identified. If the answer depends on a book, ask for its full title and author; otherwise keep reflecting without a book tool. |
| `clarification` | Ask for the missing reading context, answer nothing book-specific, declare no evidence, and call no other tools this turn, even for another part of the message. You do not need to copy the question verbatim: after safety review, the application sends Librarian's validated question to the reader, and their answer reaches the next turn. |
| Previous released turn was a clarification and `context_resolution.status` is now `confirmed` | The reader has answered and the chapter is validated. Do not call `librarian_route` again or ask the question again; call `librarian_search` with the confirmed work and version. |
