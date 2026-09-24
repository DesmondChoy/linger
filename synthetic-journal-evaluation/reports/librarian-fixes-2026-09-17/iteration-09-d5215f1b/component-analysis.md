# Release component — iteration 9

The release component completes 11/12 strict case passes and releases an answer in all twelve cases. Its aggregate targets_pass=true does not meet the full strict contract: identity-theme still fails strength and evidence recall, and its response again contains an unsupported reverse causal interpretation. The direct/notebook helper was not rerun in this targeted batch.

Every reply and review sequence was inspected. All final quote_checks are true; final source quotation bindings and the two evidence-limit replies were checked separately. Source-local private excerpts are not independent proof that every interpretation follows.

| Case | Observed result and assessment |
| --- | --- |
| rabbit-watch | Credible pass after correction. Full visible curiosity quotation now includes its comma; watch/waistcoat novelty and pursuit are grounded. |
| drink-me | Credible pass. Exact complete label, Chapter1 location and direct answer. |
| pool-of-tears | Credible pass. Correct origin in Alice's tears when nine feet high; no invented source. |
| caucus-prizes | Credible pass. Everybody-wins quotation plus comfits and thimble supported by two separate records. |
| giant-puppy | Credible final pass after removing a size descriptor absent from the declared record. Stick, thistle, tiring and escape remain accurately grounded; quotation complete. |
| identity-change | Credible pass after adding the separate declaration for “Who are _you?_”. All quoted occurrences now fully bound; size-change confusion is grounded. |
| father-william | Credible pass. Correct recitation and Chapter5 location, with a matching quotation. |
| pigeon-serpent | Credible final pass. Review removes the claim that Alice was hunting or would eat this Pigeon's own eggs; final reply accurately describes the Pigeon's general egg-eating assumption, neck judgment and refusal to reconsider. |
| identity-theme | Supported failure, not only a gold dispute. The reply states that uncertainty about identity makes each new size harder to understand; the supplied excerpt explicitly establishes size changes confusing Alice, not that reciprocal causal direction. Prove accepts the whole group from “not myself”. The unchanged strength/range checks also fail. Unlike iteration8's repaired bounded reading, this version should not be relabeled a semantic pass by approving alternative evidence. |
| exact-caucus-quote | Credible pass. Full canonical Dodo quotation, including emphasis, with visible Chapter3 citation. |
| future-cheshire | Credible pass. Reports no supporting passage found within Chapters1–5 and does not disclose a future scene or assert whole-book absence. |
| absent-spaceship | Credible pass. Reports no support found in the authorized range without inventing an event or location. |

The release summary records 673,779 input tokens, 39,592 output tokens and 80 requests, including nested agent work. Mean latency is37.0 seconds and p95 is78.9 seconds. These numbers describe this batch; its changed model setting and stochastic content prevent attributing every difference from iteration8 to high reasoning.

Evidence: [release artifact](suite-release.json), [strict failures](suite-release.status.json), and [batch configuration/source check](summary.json). No expected answer or grade was changed.
