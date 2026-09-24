# Librarian release component — iteration 4

All 12 cases completed with `openai:gpt-5.6-luna`. The batch’s strict case checks pass for 11 and fail for `identity-theme`. Every case released a Muse response after a final Provenance pass; every declared citation resolved, and no retrieved record exceeded its permitted chapter. Manual review nevertheless finds a remaining prose-level limitation in `future-cheshire`, so its mechanical pass is not a clean semantic pass. No evaluation, runtime, or expectation was changed for this analysis, and no additional model calls were made.

The primary evidence is [the complete saved release artifact](suite-release.json), including each case’s reply, Librarian assessment, and all Provenance input/output exchanges. [The run log](suite-release.log) records execution; [the batch summary](summary.json) records the strict checks. Reviews below inspected the actual final replies and frozen source records, not only the aggregate grades. Remote trace visibility was not checked.

## Why the native release target still fails

| Measure | Observed | Target | Result |
| --- | ---: | ---: | --- |
| Complete case set | 12/12 | Complete | Pass |
| Mean evidence recall | 0.9167 | ≥0.90 | Pass |
| Citation-weighted precision | 10/12 = 0.8333 | ≥0.95 | **Fail** |
| Strength accuracy | 11/12 = 0.9167 | ≥0.90 | Pass |
| Answerable release rate | 10/10 | ≥0.90 | Pass |
| Retrieved spoiler exposures | 0 | 0 | Pass |
| Citation resolution | All resolve | All resolve | Pass |

`native_release_targets` is therefore a real aggregate failure, not a second independent defective case. The two `identity-theme` citations account for both gold-unmatched citations. Native precision divides total gold-matching citations by total citations, rather than averaging passing cases. The batch additionally requires perfect recall, precision, and correct strength for every individual case; it records all three `identity-theme` mismatches even though the native mean recall and strength thresholds are met. See [metric calculation](/Users/kevinmanuel/Documents/REPO/linger/evals/librarian/live_validation.py:246), [aggregate targets](/Users/kevinmanuel/Documents/REPO/linger/evals/librarian/live_validation.py:369), and [strict batch checks](/Users/kevinmanuel/Documents/REPO/linger/synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/run_batch.py:136).

## All case reviews

| Case | Recorded result and reviews | Observed answer and independent assessment |
| --- | --- | --- |
| `rabbit-watch` | Pass; revise → pass | Identifies the watch taken from a waistcoat pocket as the immediate trigger and quotes “burning with curiosity.” The first draft added “riverbank”; the supplied record says only “bank.” Revision removes that unsupported detail while preserving the answer. **Credible pass**, with actual repair exercised. |
| `drink-me` | Pass; pass | Answers “DRINK ME,” from Chapter 1 record 0165–0192. The source’s label wording and chapter metadata support the answer. The trailing comma is awkward but does not alter the fact or quotation. **Credible pass**; the prior citation-normalization problem does not recur. |
| `pool-of-tears` | Pass; pass | Says the pool came from Alice’s own tears when she was nine feet high. Chapter 2 record 0375–0401 explicitly identifies that origin. **Credible pass**, not a generic thematic answer. |
| `caucus-prizes` | Pass; pass | Says everybody wins, participants receive comfits, and Alice receives a thimble. Two overlapping Chapter 3 records establish those distinct details; the second supports Alice’s own prize. **Credible pass** with meaningful multi-record support. |
| `giant-puppy` | Pass; pass | Describes the stick, repeated dodging behind the thistle, and escape when the puppy tires. Record 0906–0929 supplies all those events. **Credible pass**; the explanation answers how she avoids being trampled rather than merely naming the encounter. |
| `identity-change` | Pass; revise → pass | Explains Alice’s inability to explain herself through repeated changes and confusion about size. Provenance requests that undeclared literal quotations be declared or paraphrased; revision paraphrases them and retains the declared “Who are _you?_” quotation. Record 0960–1016 supports the final explanation. **Credible pass**. |
| `father-william` | Pass; pass | Identifies “You are old, Father William,” in Chapter 5. Record 1004–1056 includes the Caterpillar’s instruction and Alice beginning the poem. **Credible pass**; the trailing comma is presentational, not a wrong title. |
| `pigeon-serpent` | Pass; pass | Explains the long neck, egg-eating generalization, fear for the eggs, and Alice’s doubtful identification as a girl. Record 1179–1219 supports the factual contributions. “Reasoning from fear rather than evidence” is rhetorical interpretation: the Pigeon does cite observations, but draws an invalid conclusion. **Pass with limitations** for that overcompressed wording, without a material factual or spoiler defect in the answer. |
| `identity-theme` | Fail: strength, recall, precision; revise → pass | Uses canonical Chapter 2 identity-testing and Chapter 5 size/memory passages outside both fixed gold ranges. The final answer provides a relevant literary interpretation and repairs joint source mappings. **Potential false negative**, detailed below; saved failures remain unchanged. |
| `exact-caucus-quote` | Pass; pass | Gives the Dodo’s exact “_Everybody_ has won, and all must have prizes” passage, correctly locates it in Chapter 3, and explains the immediate question about the race’s winner. Canonical underscores are preserved. **Credible pass**. |
| `future-cheshire` | Pass; pass | Gives no road-choice advice, cites nothing, and does not reveal a later chapter or plot outcome. However, it asserts absence from the eligible text and invites sharing the passage “when you reach it,” presupposing its later occurrence. **Potential false positive** for bounded-answer/spoiler semantics; see below. |
| `absent-spaceship` | Pass; revise → pass | The original categorical claim that Alice does not repair a spaceship in chapters 1–5 is rejected because retrieval nonfinding is not exhaustive proof. After another bounded search, the released answer says only that the supplied passages identify no such scene or location. **Credible pass**, and a useful contrast to `future-cheshire`. |

## Identity-theme: relevant alternative evidence, not fabricated citations

The exact query is “How do Alice’s changing size and uncertain identity reinforce each other?” with a Chapter 5 ceiling. The saved case expects `weak` and accepts only Chapter 4 lines 762–770 and Chapter 5 lines 966–981. It contains no separate rationale requiring a whole-book interpretation. See [the case definition](/Users/kevinmanuel/Documents/REPO/linger/evals/librarian/cases.json:13).

The selected Chapter 2 record 0327–0360 shows Alice asking whether she has changed, questioning who she is, comparing herself with other children, and testing memory, knowledge, and speech. The Chapter 5 record 1004–1056 explicitly couples inability to remember as before with inability to maintain the same size. Together they provide meaningful support for the requested relationship within the permitted scope. They do not literally demonstrate a psychological feedback mechanism, but the reader requests interpretation, and the final synthesis says the passages “suggest” the reciprocal instability. A sufficient judgment for this bounded literary answer is defensible. The strength reason overstates the Chapter 2 record alone when it says altered size leads directly to the identity question; the paired Chapter 5 record supplies the explicit bodily connection.

Provenance initially rejected unmapped opening/closing synthesis and a claim mapped to only one of the two necessary sources. The revision maps the joint interpretation to both records; the final review confirms those repairs. Both citations resolve exactly, remain within the ceiling, and support the topic. Their zero precision and recall arise from fixed range overlap, not absent or invented evidence. This is a **likely gold-coverage/strength-expectation mismatch**, with the intended calibration still requiring a human decision. Do not relabel the case or widen its gold solely to clear the batch. Review alternative accepted passages and the intended `weak` rationale together.

## Future-Cheshire: advice withheld, future implication remains

The complete released reply is:

> The eligible text through chapter 5 doesn’t contain the Cheshire Cat’s road-choice exchange, so I can’t answer that from your current reading boundary without risking a spoiler. If you share the passage when you reach it, I can explain the advice within your spoiler limit.

The positive regression is real: there is no road advice or description of the later encounter. Librarian returns `none`, no canonical evidence is released, and Provenance passes without findings. But the passage does **not** establish complete absence from chapters 1–5, and “when you reach it” implicitly confirms the premise of an upcoming passage. Those are avoidable claims. The spaceship case in this same run demonstrates the safer bounded formulation and shows that Provenance can recognize the nonfinding/absence distinction, but did not do so here.

The metric named `spoiler_exposure` checks returned evidence chapter numbers; it does not inspect the reply for future-event implications. With no returned records, it is false regardless of the reply’s semantics. See [the actual check](/Users/kevinmanuel/Documents/REPO/linger/evals/librarian/live_validation.py:274). This is a confirmed coverage limitation and a supported wording concern, not proof that the actual Cat advice leaked. A future authorized correction should keep the no-evidence statement limited to supplied passages and make any invitation conditional on the reader choosing to share text, without predicting where or whether it appears. Verify the actual response wording, not only zero citations and the numeric spoiler flag.

No optional semantic evaluator was invoked. This report is an independent reading of the saved local evidence; its interpretations remain separate from the unchanged recorded grades.
