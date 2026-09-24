# Component evaluation analysis: iteration 3

All twelve cases ran in each component on the same frozen revision. The notebook helper set passes every per-case check for 11/12 cases. The release component passes every per-case check for 10/12. Its native aggregate `targets_pass=true` permits the remaining failures at the configured thresholds; the batch correctly rejects this as an all-case pass. No released response exposes later material, and all released citations resolve.

| Case | Notebook assessment | Released behavior and assessment |
| --- | --- | --- |
| rabbit-watch | Sufficient direct watch/waistcoat evidence; correct range | Names the waistcoat pocket, watch and curiosity in Chapter 1. Credible answer; the final rhetorical gloss is unnecessary but consistent with the passage’s lack of attention to escape. |
| drink-me | Direct label evidence | Gives the exact label with Chapter 1 attribution. Credible pass. |
| pool-of-tears | Direct origin evidence | Quotes that Alice wept the pool while nine feet high. Exact canonical text and Chapter 2 scope. Credible pass. |
| caucus-prizes | Direct winner/prize evidence | Everybody wins; describes comfits and Alice’s thimble. Credible pass. |
| giant-puppy | Direct action sequence | Stick, thistle, dodging and escape are supplied by Chapter 4. Credible pass. |
| identity-change | Direct Chapter 5 exchange | Quotes Alice’s inability to explain herself and relates repeated size changes to confusion. Interpretation stays with the provided exchange. Credible pass. |
| father-william | Direct command | Identifies the poem and Chapter 5. Credible pass. |
| pigeon-serpent | Relevant encounter evidence | Revised answer explains long neck, eggs and the Pigeon’s inference. Resolvable exact citations and approved bounded response. Credible pass. |
| identity-theme | Sufficient label with Chapters 2/5 fails the frozen weak + Chapters 4/5 key | Actual response repair fails too: an overconfident reciprocal interpretation is narrowed, but a new opening remains unmapped and an altered-memory claim is assigned to a passage that lacks it. Two revise verdicts lead to safe decline. Do not attribute this release failure solely to the disputed key. |
| exact-caucus-quote | Direct exact quotation evidence | Quotes “_Everybody_ has won, and all must have prizes.” with Chapter 3. Credible pass. |
| future-cheshire | Correct bounded absence through Chapter 5 | Muse initially says the reader can continue to the chapter where Alice meets the Cat, confirming a future event without authorized text. Provenance correctly rejects that preview. The final safe fallback leaks no answer but incorrectly implies the reader’s position is unknown and does not complete the bounded-absence answer. Genuine response failure, masked by aggregate thresholds. |
| absent-spaceship | Correct unsupported premise | Revised response says no supplied Chapters 1–5 passage locates such a repair and suggests a different book or scene. It invents no spaceship event and does not claim exhaustive later search. Credible bounded-absence pass. |

The `identity-theme` notebook mismatch remains a review decision about the intended question and acceptable textual anchors. The release defects require runtime repair independently: simplify the whole candidate before regenerating mappings, retain only supported source contributions, and avoid future-story previews when retrieval returns none. Keep Provenance’s spoiler rejection; do not weaken safety checks to release the initial Cheshire response.

Complete release usage: 582,218 input tokens, 22,340 output tokens, 75 provider requests. This is the release component only. The notebook execution used its actual case helper/scorer, not every interactive demonstration cell. Evidence: suite-direct.json, suite-release.json, progress files and status files. Raw results remain unchanged; these are coding-agent assessments, not human adoption or extra provider grading.
