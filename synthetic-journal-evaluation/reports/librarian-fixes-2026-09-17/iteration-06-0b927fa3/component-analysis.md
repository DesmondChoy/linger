# Librarian components — iteration 6

Both twelve-case runs finish with **11/12 strict passes**. `identity-theme` remains the sole case failure in each. Every release case delivers a Muse answer; future-Cat and spaceship correctly report the limited search outcome without confirming a future scene. The direct run executes the notebook's real case helpers, not every notebook cell.

Direct strength accuracy is 91.67%, with mean recall and precision 95.83%. Release reports strength accuracy 91.67%, recall 95.83%, citation precision 82.35%, answerable release rate 100%, and all declared citations resolving within scope. Release precision counts declarations: identity-theme repeats its two sources across three groups, so the three off-gold declarations lower the aggregate more than one unique alternative record would. This is the metric as implemented, not evidence of three independent invented sources. No grades or gold were changed.

## Every case

| Case | Direct result | Released result and semantic review |
| --- | --- | --- |
| rabbit-watch | Correct watch/waistcoat trigger and record. | Grounded curiosity and pursuit. Exact quoted fragment bound. Parenthetical discussion of source line wrapping is unnecessary user-facing detail. |
| drink-me | Correct label and record. | Exact label, matching declaration and visible chapter. |
| pool-of-tears | Correct origin in Alice's own tears. | Correct height/origin and exact bound quotation. |
| caucus-prizes | Both everybody-wins and Alice's thimble supported by two records, fixing iteration 5's overextended direct reason. | Correct distribution and Alice's prize, complete mappings. |
| giant-puppy | Correct stick, thistle, dodging and escape. | Grounded account and canonical cart-horse comparison. |
| identity-change | Correct relationship between changing sizes and uncertainty. | Useful grounded explanation. Multiple extra quoted fragments sit inside claim mappings but only one is explicitly bound as `exact_quote`; passing all declared quotes is not exhaustive quotation verification. |
| father-william | Correct named poem. | Correct title and chapter; no new plot claim. |
| pigeon-serpent | Correct appearance and eggs reasoning. | First review catches missing summary mapping and unsupported mushroom detail; revision passes. It also narrows the egg claim. Final quoted “a kind of serpent.” carries a terminal period whereas source continues with a comma; the shorter declared snippet does not verify that full visible quotation. |
| identity-theme | Sufficient with Chapter 2 and 5 alternatives; gold expects weak and Chapter 4 plus 5. Recall/precision 0.5. | Same strict mismatch. Review narrows stronger reciprocal causal interpretation and adds actual joint mappings. Final literary reading is useful but the strength/alternative-gold decision is still unresolved. Extra “Who are you?” omits canonical emphasis and lacks an exact-quote declaration. |
| exact-caucus-quote | Correct Dodo announcement record. | Requested quotation retains canonical emphasis and wording; full quotation is bound. |
| future-cheshire | None, no returned evidence. | Correct limited statement that no supporting passage was found through Chapter 5. No false unknown-progress fallback or future-scene invitation. |
| absent-spaceship | None, no returned evidence. | Correct limited absence-of-evidence response; does not invent a location or event. |

The quotation limitations are actual review coverage issues, not off-gold source selection. A mapped sentence may contain extra quotations; a claim audit does not establish that every such quotation is declared or exact. The next Muse/Provenance clarification must preserve public exactness while checking all visible fragments, including fragments within mapped claims.

The identity case still needs the human decision described in `../expectation-proposals/component-identity-theme-decision.json`. Neither silent weakening of its expected strength nor repeated identical runs to chase a lucky pass resolves that ambiguity. The final reply presents a thematic reading, while the wording “reinforce” can invite an unproven reciprocal causal account. Its revised version no longer asserts every size change proves Alice became someone else.

Read all direct reasons and selected IDs, all twelve final replies, and the complete source mappings and reviews for repaired or disputed cases in `suite-direct.json` and `suite-release.json`. The chapter-only spoiler metric does not establish prose safety; the two no-evidence replies were separately inspected. All runtime hashes remained unchanged through completion (`summary.json`).

## Mapping diagnostic

The optional four-case diagnostic failed to save its report because SDK usage cost is Decimal and the adapter used ordinary JSON serialization. The first result therefore has no recoverable local review artifact; subsequent progress writes also fail. Treat this diagnostic as an execution failure with unknown semantic outcome, not a passing model check. Preserve `suite-mapping.log` and count the batch. The adapter fix uses Pydantic's JSON serialization for RunUsage and an offline Decimal-cost regression before another live attempt.
