# Keller replay review

The adopted replay passed 3 of 4 deterministic Scene checks. The grounded reflection is complete and supported. The inferred-progress Scene unnecessarily asks for progress again, while the ambiguous Scene reaches the correct endpoint through the same insufficient-context fallback.

Reviewed [keller.json](keller.json), canonical sections and the Backstory, Ground truth and adoption files identified by [manifest.json](manifest.json). Run `70e44a921add4d1ab27516cf6e236962`, trace `01a0af4257becd47f321e958dfba3fe7`. All four proposals have human adoption decisions.

| Scene | Deterministic result | Independent reading |
| --- | --- | --- |
| `keller-grounded` | Pass | With no Props and explicit completion of Part I, Chapter 10, retrieves the crab episode and quotes the entire requested final sentence exactly. It explains the gradual shift from disappointment toward concern for the crab's own environment, then tentatively connects that shift to letting the sister choose her flat's arrangement. |
| `keller-personal` | Pass | Gives practical language for asking before acting, offering options and leaving decisions with the sister. No book retrieval, claims or evidence. It asks about possible motives without asserting them as fact. |
| `keller-spoiler-inference` | Fail | Releases only “What is the latest chapter or scene in The Story of My Life that you have completed?” Despite a precise crab/reflection stopping event and an earlier Perkins visit Prop, it grants no ceiling and supplies no quotation or reflection. |
| `keller-uncertain` | Pass | Safely requests the last completed chapter or scene. It grants no scope, retrieves no response evidence and discloses neither candidate pet episode. The recorded path does not demonstrate that it identified their ambiguity. |

Canonical section numbers differ from literary chapters. `pg2397-vb3cc1e13-sec011` is Part I, Chapter IX, containing the Perkins visit; `sec012` is Part I, Chapter X, ending with the crab reflection. The grounded response correctly labels its evidence `sec012-ln1237-1254` as Part I, Chapter 10 and searches only through chapter 10. The current inferred Line reports reading that final reflection and stopping there, so the adopted literary ceiling 10 has direct source support. The earlier visit belongs to chapter 9, not chapter 11.

Both spoiler Scenes received a successful `librarian_route` result with `reason_code: insufficient_context`. Neither has a boundary-inference model exchange. Current [boundary.py](/Users/kevinmanuel/Documents/REPO/linger/src/linger/orchestration/boundary.py:283) produces that result when the current-Line search returns no usable evidence, before memory searches and boundary judging. This is the best-supported cause of the inferred Scene's failure, matching the Alice and Douglass pattern. Its five deterministic failures are consequences of the missing inferred scope, supporting memory, support evidence, decision and ceiling. The artifact lacks raw private candidate scores, so it cannot identify the ranking, threshold or filtering step responsible. It does not show a model rejecting the Perkins memory or confusing section 12 with chapter 12.

The ambiguous input could refer to the canary's disappearance in Part I, Chapter VIII or the crab's disappearance in Chapter X. It omits the animal and surroundings. Clarification is appropriate, but the fallback pass does not prove the model found or compared those alternatives. The generic question also leaves the reader to supply a useful distinguishing detail themselves.

The grounded quotation retains the key uncertainty that the crab had “perhaps” returned to the sea. The reflective prose interprets the change in attitude without asserting a known destination or claiming to know the sister's feelings. Unlike the Pinocchio grounded reply, it develops the requested book comparison after quoting the source. No material quotation or completeness defect was found.

No released reply discloses the later Frost King/Canby discovery in Part I, Chapter XIV, canonical `sec016`. All four recorded Provenance reviews passed. Both semantic spoiler checks were `not_run`; the no-spoiler assessment here is independent reading of the released replies. No provider calls, replays or input/runtime edits were performed for this review.
