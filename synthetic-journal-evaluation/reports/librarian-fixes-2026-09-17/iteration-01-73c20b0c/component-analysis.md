# Component evaluation analysis

Both the notebook helper set and Librarian-to-Muse release set completed all twelve cases on the same frozen runtime. Eleven cases in each set passed every per-case check. All direct citations resolved, all release citations passed deterministic validation, and no case exposed evidence beyond its confirmed chapter. These known-ceiling tests do not exercise boundary inference.

| Case | Direct and release assessment | Observed release behavior |
| --- | --- | --- |
| rabbit-watch | Credible pass | Explains the waistcoat pocket and watch as the trigger for chasing. |
| drink-me | Credible pass | Gives the actual bottle-label wording. Canonical paragraph normalization resolves. |
| pool-of-tears | Credible pass | Identifies Alice's own tears with the requested bounded source. |
| caucus-prizes | Credible pass | Everybody wins; explains the prizes and Alice's thimble. |
| giant-puppy | Credible pass | Describes the stick, thistle, avoidance and eventual escape. |
| identity-change | Credible pass | Quotes the Caterpillar exchange and links repeated changes to confusion. |
| father-william | Credible pass | Identifies the poem with the exact instruction. |
| pigeon-serpent | Credible pass after revision | Uses neck shape and eggs to explain the Pigeon's reasoning. All required ranges survive release. |
| identity-theme | Potential false negative; expectation decision pending | Both judges find sufficient support. Direct evidence uses Chapter 5's opening and later size regulation; release also uses Chapter 2's identity doubt. The saved case instead requires weak strength and Chapter 4 plus Chapter 5 ranges. Those metrics fail accurately against the current answer key, but the retrieved passages answer the literal thematic question. No key was changed. |
| exact-caucus-quote | Credible pass after revision | Releases the exact everybody-wins quotation rather than paraphrasing it away. |
| future-cheshire | Credible bounded-absence pass | Explicitly limits absence to Chapter 5 and gives no road advice. |
| absent-spaceship | Credible bounded-absence pass | Does not invent a spaceship event or claim to have searched later chapters. |

Release usage is now available across all nested roles: 735,674 input tokens, 27,428 output tokens and 96 provider requests. This is the release component's usage, not the entire batch's cost. All twelve cases released Muse responses; the failed aggregate target is caused by identity-theme's saved strength/range expectations. The notebook run executed its actual twelve-case helper and scorer, not every interactive demonstration cell.

Evidence: `suite-direct.json`, `suite-release.json`, their progress files and logs. Smoke stages are reviewed separately in `smoke-analysis.md`. Saved native grades remain unchanged; these assessments are coding-agent analysis, not independent human adoption or additional provider grading.
