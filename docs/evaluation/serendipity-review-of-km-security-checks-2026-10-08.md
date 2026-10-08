# Serendipity review of `km-security-checks`

Reviewed on 2026-10-08 by the Serendipity owner, against `origin/km-security-checks`
(6 commits ahead of `main`, last `38dd85d`). This is a review only; the branch
was not changed.

## What the branch changes for Serendipity

| Change | Where | Effect on Serendipity |
|---|---|---|
| Incoming chat messages have personal data redacted, and credentials blocked, before any agent runs | `apps/backend/chat_turn.py` (`validate_user_input`) | The reader's cue reaches Serendipity already redacted. |
| The outbound web gate checks credentials only | `src/linger/agents/serendipity/tools.py`, `_private_web_input`: `contains_personal_data_or_secret` → `validate_credentials(...).blocked` | Personal data in a web query or page URL is no longer blocked by Serendipity itself. |
| Memory capture and curation check credentials only | `src/linger/services/memory.py`, `src/linger/orchestration/curation.py` | Stored records are not checked for personal data. |
| Tests that blocked an email address in a URL are deleted | `tests/test_serendipity_public_source_access.py` | The behaviour above is no longer tested. |
| `ProviderCredentialGuard` added to `build_serendipity_agent` | `src/linger/agents/serendipity/agent.py` | No conflict in behaviour. A merge conflict with `feat/serendipity-self-improvement`, which also adds a capability on the same line; keep both. |

## Assessment

Redacting the incoming message is a stronger first line than Serendipity's
gate, and blocking credentials at every agent is an improvement. The concern
is that the branch removes the second line rather than adding a first one.

Serendipity is the only reasoning role that sends text to a third-party
service, so its outbound gate is the last control before private data leaves
the system (risk register R4, OWASP LLM02). After this branch, personal data
can still reach a web query by three routes the entry-point redaction does not
cover:

1. **Stored memories.** Records written before redaction existed, or text a
   model composes during curation, are not checked for personal data. The
   model may copy from them into a query.
2. **Model-composed queries.** The copied-wording check still blocks runs of
   three copied tokens, which catches most copied emails and phone numbers,
   but not a detail the model paraphrases or reassembles.
3. **Supplied or composed URLs.** The deleted tests covered exactly this.

## Recommendation

- Keep personal-data detection in Serendipity's outbound gate, alongside the
  new credential check:
  `contains_personal_data_or_secret(text) or validate_credentials(text).blocked`.
  It is cheap and runs only on outbound queries and URLs.
- Restore the two deleted email-in-URL tests.
- When merging, keep both capabilities on the Serendipity agent:
  `capabilities=[SerendipityOutputValidation(), ProviderCredentialGuard()]`.
- After merging, rerun `tests/test_serendipity_public_source_access.py` and
  the Serendipity component suite; the gate change should not affect it,
  since component fixtures contain no personal data.

## Cross-agent impact of the recommendation

- **Serendipity:** outbound gate unchanged from `main`; credential blocking
  added on top.
- **Muse, Librarian, Provenance, Sculptor:** no effect; their checks on the
  branch are unchanged by this recommendation.
