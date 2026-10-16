# How the Librarian design evolved

[Open the visual HTML report](design-history.html) for the interactive decision
timeline, architecture comparison, and illustrated failure examples.

Prepared September 24, 2026 from repository history and Beads at `1facc55`.
Extended October 14, 2026 against `librarian-attempts` at `cac9477`, which
contains upstream `9a5c074`. The original September experiments and their
interpretations remain historical records. The later sections trace changes
through the current runtime. This update introduces no runtime changes or new
evaluation results.

The first design concentrated on finding accurate, spoiler-safe passages.
Implementation and broader experiments exposed additional problems: establishing
reading permission, preserving conversational context, retaining useful
evidence, and checking how an answer uses it. Those failures explain much of
the current separation between application services and Librarian's model tasks.

The [experiment report](report.md) contains the detailed outcomes and recurring
failures. The [attempt chronology](chronology.md) records individual interventions.
This document connects those experiments to the earlier design decisions and
records the later changes without treating old scores as current validation.

## Evidence and limits

The account below distinguishes documented reasons from interpretation. Its
sources are versioned designs, commit history, Beads descriptions and completion
notes, saved experiments, and the linked GitHub architecture discussion.
Beads IDs identify historical records that can be read with `bd show <id>`.
A closed ticket establishes recorded completion, not current reliability.

The original [experiment decision log][decisions] records decisions, reasons,
evidence, and outcomes during the repair series. The separate
[report-production log](decisions.tsv) records how the September 24 analysis was
assembled. It is not the design-decision log.

The records do not preserve every discussion or rejected alternative. External
team chat, observability, error tracking, and analytics were unavailable during
this reconstruction. Current source code establishes behavior; an older design
or ticket establishes what was intended or understood at that time.

## The first proposal already included hybrid retrieval

The [August 10 design at `205252c`][first-design] proposed deterministic offline
preprocessing followed by online evidence retrieval. Books would become
450-token chunks with 75-token overlap. Keyword and semantic search would feed
fusion, deduplication, and reranking. Librarian would judge whether the selected
evidence was sufficient, weak, or absent and return at most five passages.

The model could choose retrieval strategies and call retrieval tools. Trusted
application context supplied an explicit reading boundary. The design left
models and fusion details undecided and described the numerical defaults as
initial values requiring evaluation.

Two distinctions survived the subsequent changes. A relevance score does not
prove that a passage supports an answer. A Librarian evidence bundle does not
authorize publishing that answer. Muse drafts, Provenance reviews, and the
application enforces release checks. Beads `linger-xgu` records these original
responsibilities.

## Canonical text came before a fixed retrieval strategy

The [August 11 revision at `7935aca`][corpus-design] stepped back from committing
the corpus to the proposed chunk-and-index pipeline. It established immutable
source text, exact-layout Markdown chapters, and a metadata-only catalogue.
Indexes became replaceable derived artifacts. Direct chapter reads became the
retrieval baseline.

This separated citation identity from search tuning. Changing a window size,
embedding model, or ranking method would not require changing authoritative
book text. Retrieved excerpts still had to resolve to that text.

The revision explicitly required measuring direct reads, comparing additional
retrieval methods, and adding the smallest approach that materially improved
quality, latency, or context use while preserving citation resolution. It does
not preserve a fuller meeting-style explanation of the change.

The historical sequence is therefore hybrid retrieval proposed, then a simpler
corpus and direct-read baseline, then hybrid retrieval selected through
measurement. Describing direct reads as the first-ever proposal would omit the
August 10 design.

## Measurement justified hybrid retrieval and reranking

Beads `linger-ibq.5` required five configurations on the same Alice cases:
direct canonical reads, BM25, semantic search, hybrid without reranking, and
hybrid with reranking. Safety and exact citation resolution were prerequisites.
Evidence quality determined selection, with latency and cost breaking close
results.

At the original selection point, direct reads had approximately 50% recall.
Reranked hybrid retrieval reached 91.7% recall and 76.4% candidate precision.
The ticket records approximately 454 ms p95 across five repetitions. Those
measurements supported paying the extra local ranking cost for better evidence
selection. See the [selection-era design at `9a5d589`][selection-design].

The subsequent saved report has different precision and timing values. The
[historical measurements in the maintained design][current-design] identify
that later snapshot. These reports must not be combined as though their
configurations and graders were unchanged.

Provider-backed validation then exercised Librarian, Muse, Provenance, and
release. It distinguished candidate quality from final citation quality.
However, the initial 12 Alice cases supplied known chapter boundaries. Their
success did not establish reliable inference of reading progress across books.

## Reading permission became a separate inference task

Boundary ownership changed during development. Beads `linger-hm6` assigned
temporary boundary inference and clarification to Muse on August 11. The
application enforced the typed boundary, and reading progress was not persisted.

Beads `linger-lfh`, implemented in commit `23ee593` on August 28, replaced an
interim application regex parser with Librarian-owned semantic inference. A
reader can describe reaching the Caterpillar without knowing its chapter number.
The system needs to locate that event before it can establish answer scope.

The design separated private localization from answer retrieval. Private
inference could inspect the work and propose a boundary with supporting
locations. Application code validated the proposal. A second retrieval searched
only within accepted permission. Private later-chapter text could not become
Muse's answer evidence merely because localization found it.

The August 30 tightening, recorded in `linger-kln` and commit `cb48cec`, addressed
another distinction. Curiosity can identify an event without proving that the
reader has reached it. Recognizing a title or associating a memory with a book
does not establish progress. Stronger identity and reading-support checks
followed, while explicit reader-confirmed progress remained authoritative.

These early descriptions refer to full-work inference. At the October 14
snapshot, private inference
localizes numbered chapters in the main part. Other parts and named units need
explicit scope. That limitation matters for books with letters or supplementary
material.

## Session context removed an unnecessary dependency on saved memory

Beads `linger-bw7v` records a two-turn Caterpillar failure on September 5. The
reader first described reaching the scene, then requested an exact quotation.
Muse received the conversation history, but Librarian received only the latest
question and no saved memories because capture was disabled.

Librarian located Chapter 5 with confidence 0.98. The application still rejected
the proposed authority because locating a passage from the current question
alone did not prove reading progress. The missing support was already in the
conversation.

Commit `4abda38` passed bounded original reader statements into inference and
introduced exact canonical paragraph grants. A reader can receive a quotation
from a demonstrated passage without being treated as having completed the whole
chapter. Neighboring text remains outside that grant.

The [original passage design][original-passages] compared alternatives. A
dedicated passage extension preserved the distinction from confirmed chapter
progress. Treating session statements as saved memory would have blurred their
provenance and made continuity depend on capture. The
[maintained passage rationale][passages] preserves that separation.

Saved memories, original session statements, and confirmed progress therefore
play different roles. Grounded reflection with explicit permission does not
require stored memory. Session-supported passage permission also works with
memory capture disabled.

## More books required literary locations instead of storage ordinals

Alice's chapter structure hid an assumption that became visible in Douglass and
Keller. A stored section number is not necessarily a literary chapter number.
Keller's edition begins with a dedication and an editor's preface. Its `sec003`
is Chapter 1, `sec011` is Chapter 9, and `sec012` is Chapter 10. Douglass's Chapter
7 is stored in section 10 after prefatory material.

Beads `linger-vjz5` required reviewed mappings for source order, natural chapter,
part, and named-unit identity. The implementation preserved canonical bytes and
existing IDs while propagating those locations through retrieval and release.
It enabled the existing section-based corpora after compatibility checks.

This changed the interpretation of location metadata, not the books themselves.
A citation containing `sec012` does not prove that the system retrieved Chapter
12. See the [chapter-resolution examples](report.md#chapter-identity-and-inclusive-search-permission).

## Consistent retrieval needed shared services and focused requests

Two kinds of failure motivated the shared book-evidence operation.

First, Beads `linger-htzz` records Serendipity returning `no_evidence` while the
direct Librarian path used by Muse retrieved a real Chapter 5 passage. Both
callers were moved onto shared application-owned candidate recovery, scope
filtering, evidence assessment, and canonical-ID validation. Exact-passage
grounding could use the same judgment without broad search.

Second, reader messages mixed tasks. The saved Animal Farm request includes
Snowball's expulsion, recognition of the dogs as the earlier puppies, the
windmill reversal, a quotation request, and a workplace reflection. Searching
the entire message made several different needs compete for relevance.

Focused planning separates book needs before retrieval. A conceptual split is
dog recognition, the final windmill stopping event, and the leadership quotation.
This example illustrates the design rather than reproducing a saved planner
transcript. The personal reflection supplies response context without becoming
a factual claim about the book.

Beads `linger-hwxg` and `linger-lp22` record the associated recall concern.
Decomposition can omit a legitimate request. The application therefore retains
uncertain needs and searches original reader text alongside focused queries.
Assessment checks the original request and can recover omitted needs using
exact reader spans. Discovery of a missing need during assessment does not
automatically trigger another search. Candidate limits and semantic omissions
remain possible. [Examples and limits](report.md#focused-queries-with-protection-against-omitted-requests)

## Candidate retention and token windows repaired different losses

The [retrieval decision note][retrieval-design] documents Keller's canary passage
ranking second lexically and fourth in fusion but twelfth after reranking. A
small private selection discarded it. With only the crab episode remaining, an
ambiguous lost-pet description could appear more specific than it was.

The private path retained the union of independent lexical and semantic
candidates within a 20-record budget. It also preserved overlapping records
because the decisive sentence might appear in only one window. Public retrieval
kept its separate thresholds and deduplication rules. A cached probe retained
both canary and crab, establishing recovery in that example rather than a
general recall guarantee.

Beads `linger-n8vx` documents a separate loss inside the reranker. The Douglass
copybook passage and original reader message formed a 707-token pair against a
512-token limit. Truncation removed the Thomas copybooks, Monday meetings, and
handwriting details. Even a focused 21-token question left a 577-token pair.

The repair scores overlapping token windows under the actual tokenizer budget
and associates the maximum window score with the unchanged canonical passage.
This lets the model see the ending. It does not calibrate relevance scores or
guarantee a high score. A saved 1,022-token probe used three windows and still
scored poorly. Query rewriting, candidate retention, and token coverage address
different failure mechanisms.

## Application-owned permission prevented handoff errors

Beads `linger-hn7j` records successful inference followed by incorrect search
permission. Keller received an inclusive Chapter 10 grant, but Muse called the
search as though the reader had only started Chapter 10. That correctly caused
the search adapter to stop at Chapter 9, excluding the requested quotation.
Pigeon similarly changed from an inferred Chapter 5 ceiling to a Chapter 4 search.

The [integration design][integration] removed model-supplied chapter state from
the search handoff. Application code now supplies the validated chapter scope
or exact-passage grant. Muse supplies the selected book identity rather than
restating the permission and risking a different interpretation.

The architecture also moved from several Agent configurations to one reusable
Agent per logical role with application-selected skills. [Issue 46][skills-issue]
explicitly describes the maintenance problem: five roles were spread across
nine configurations, making ownership difficult to inspect across builders,
prompts, and modules. Commit `d0ce6b7` organized those tasks under explicit skills.

Current Librarian skills cover request planning, boundary inference, independent
event identification, and evidence assessment. Retrieval and permission
enforcement remain application services. Reusing one Agent does not collapse
those tasks into one model call. [Runtime architecture][skills]

## Better evidence still needed stronger authorization and release review

Recovering passages did not solve unsafe inference. An ambiguous Alice growth
description received Chapter 5 authority even though the reader supplied no
mushroom detail. Real citations and exact reader spans did not make that
interpretation valid.

The [iteration-15 decision][boundary15] compared three responses: another
resolved-or-unresolved field, explanations for every omitted candidate, or an
independent identification of the current event. The first repeated the original
judgment. The second added output burden without independent evidence.

The selected approach makes a separate Librarian call without the proposed
grant or saved memories. Application code requires agreement on the chapter and
compatible canonical source ranges before accepting a positive chapter proposal.
Uncertainty, disagreement, or execution failure grants nothing. Exact-passage
authorization remains a separate path.

This adds cost and another fallible semantic judgment. Local tests establish
enforcement. Attempt 18's ambiguous controls clarified safely before the new
gate rejected anything, so that batch did not validate its rejection behavior
on a live false-positive proposal.

Release review evolved for related reasons. An exact quotation can support only
part of a sentence, and a real citation can point to the wrong episode. In the
Roses case, a claim that concealment failed cited the gardeners' earlier
intention rather than the later discovery. Repairs added checks for individual
source contributions, combined support, uncovered claims, quotation equality,
and preservation of valid content through bounded revisions.

These checks improved detection without eliminating semantic mistakes. Some
reviewers rejected valid material, and some passing answers still omitted
source-dependent claims. [Source-support examples and results](report.md#exact-quotations-source-attribution-and-combined-support)

## Evaluation changes are part of the history

Some failures came from the grading contract. Exact support-set equality rejected
additional valid evidence inside the same chapter boundary. The Alice identity
case required weak evidence even when Chapter 5 supported a qualified
interpretation of size and identity.

Approved changes admitted reviewed optional evidence and valid Chapter 5
alternatives while preserving required anchors and chapter limits. Historical
grades were not rewritten. Consequently, improved pass counts reflect both
runtime repairs and expectation corrections. The [chronology](chronology.md)
identifies those changes rather than attributing all improvement to retrieval.

The series contains 21 numbered attempts because one additional rerun was
authorized after suspected exhausted API credit. Attempt 20 contained observed
429 errors. Attempt 21 recovered substantially with the runtime and adopted
inputs held fixed, apart from the driver change permitting another attempt.
That supports an availability explanation for much of the collapse, without
proving the billing cause or explaining the remaining semantic failures.

The selected [iteration-18 checkpoint][checkpoint] recorded 26 of 29 native
Scenes and 28 of 32 judgments passing. Direct retrieval and answer release each
passed 12 of 12 cases, mapping controls passed 4 of 4, and the outside-essay smoke
test passed. It was the strongest recorded full batch, not an all-pass result
or an established normal performance range. Later integration was not a fresh
live validation of that checkpoint.

## What the September checkpoint established, and what remained uncertain

The accumulated decisions separate matching a book, locating an event,
establishing permission, retrieving a passage, judging support, and releasing an
answer. The interpretation supported by this history is that experiments exposed
places where one of those decisions had been treated as sufficient for another.
Explicit boundaries made the errors easier to detect and constrain.

The September architecture had exact canonical sources, shared retrieval,
request planning with original-text fallback, distinct chapter and passage
permission, token-aware reranking, and separate semantic review. The records
explain why those mechanisms were added more strongly than they establish the
reliability of every mechanism in combination.

The September record still included incorrect boundary proof construction, disagreement
over mandatory Animal Farm continuity evidence, Roses mapping and expectation
issues, incomplete declaration of source-dependent interpretations, and reviewer
inconsistency. Exact-passage behavior is also outside the chapter-scoped synthetic
grading contract. The [checkpoint][checkpoint] and [experiment report](report.md)
describe these limits and separate later observations from iteration-18 outcomes.

The earliest numerical defaults have no recovered empirical justification.
Several changes lack a controlled comparison against their alternatives.
Configurations, prompts, expectations, and execution conditions changed across
the repair series, so its aggregate pass rate is not a production reliability
estimate. No single historical report supplies a current latency, cost, or
quality baseline for the integrated implementation.

## September 23 to 27: several books needed separate retrieval budgets

Commit [`8c7bdba`][multi-book] let one comparison carry several confirmed book
scopes through Muse, Serendipity, Provenance, and release validation. It did
not assign one primary book or make evidence from one work authorize another.
The wider request exposed a retrieval-budget problem. One book could occupy
the shared candidate pool and displace a relevant passage from another.

On September 26, [`7012886`][per-book] gave each granted book its own search
and 20-record assessment pool. Query preparation also removed the searched
book's author-name words unless they occurred in its title or aliases. The
reader's exact spans and canonical text stayed unchanged.

The next reduction worked at the requested-part level. The planner learned to
split each named event in a sequence in [`d72b87e`][sequence-plan]. Then
[`d6b8e30`][part-routing] retained three candidates per planned query in a
clearly matching book, or in every granted book when no match dominated.
A single-book route required a best relevance score of at least 0.05 and ten
times the next book's score. Original reader text and prior statements retained
two candidates per book as fallback. These are retention decisions after
search, not permission decisions.

The September 27 commit records Scene 07's assessment pool falling from 60 to
14 passages and an offline replay retaining all 32 required passages. Those
measurements explain the reduction at that checkpoint. They do not establish
that three candidates preserve every answer, and October's retention fix
changed that production value to four.

## September 26 to 27: assessment failures became repairable

Some searches failed after retrieving the right text. The assessor could copy
one record's long ID while describing another, omit support for a requested
part, or return reader spans that did not match the input. A check performed
only after the model run discarded the whole result without allowing repair.

[`7012886`][per-book] reported ID and selection errors together.
[`3fa2c01`][assessment-repair] moved coverage and exact-span checks into the
bounded output-retry loop, then repeated the checks at the application
boundary. Useful incomplete evidence remained a valid `weak` result. Output
that still violated the contract remained invalid.

[`544d648`][short-labels] replaced long corpus IDs with local labels such as
`E1` and `E2` in assessment input. Application code maps validated selections
back to canonical IDs and replaces labels in explanations with source
locations. The labels reduce copying errors. They do not prove that the model
chose the right passage. The current [assessment dispatch][assessment-source]
retains this separation between model labels and canonical identity.

## October 1: optional retrieval experiments exposed a cost tradeoff

[Experiment 3][experiment3] tested search-only chapter descriptions,
characters, and cues for Pinocchio. Canonical quotations and citations stayed
unchanged. With the original cues, 17 of 20 practice needs reached the
assessment pool. Sculptor's first rewrite also reached 17, with one gain and
one loss. The stop rule ended the loop before a second rewrite. The once-run
sealed set reached 14 of 20 with the original cues and 16 with the rewrite.
The experiment did not meet its decision rule, and the approved cues stayed
inactive.

[Experiment 4][experiment4] changed the measure to the passages Librarian
actually selected, rather than any passage reaching its pool. Sculptor read
practice traces and proposed retaining 20 candidates per planned part instead
of three. The owner approved the steps, and the developer implemented an
explicit experiment argument. Selected-evidence results rose from 17 to 20 of
20 practice needs and from 16 to 20 of 20 held-back needs, with no losses.
The held-back set had already been used in Experiment 3. It was not an untouched
test set.

Round 1 met its predefined practice pass mark, so the loop stopped. The
Librarian read about 3.8 times as many words per practice need, and input tokens
rose about 2.5 times. These results establish the recorded experiment's outcome,
not a production quality baseline or a demonstrated second improvement round.
Reader replies were not the measure.

At the October 14 snapshot, `HybridLibrarian(read_chapter_cues=True)` remains
opt-in, and the 20-per-part setting remains an offline experiment override.
Production uses four per planned query. The experiment reports' three-record
baseline describes October 1 and must not be silently updated to today's
value. See the [hybrid implementation][hybrid-source] and
[candidate gathering][candidate-source].

## October 2: candidate reduction stopped discarding unique answer text

Commit [`5c4f4b4`][retention-fix] repaired three losses in the reduced pool.
The private retrieval output interleaves keyword, fused, semantic, and
reranker streams. Its first three records are not the three highest scores.
Keeping four records preserves a first round of those streams when they are
available, including a reranker choice that the previous cutoff could remove.

The old overlap filter could also discard a passage whose unique lines
contained the answer. The replacement removes a window only when an earlier
record contains all of its source lines within the same work, version, part,
chapter, and source hash. Partially overlapping windows remain eligible.

Finally, original-context fallback now survives independently of planned-query
routing. Identical queries reuse one search, but a routed planned query cannot
silently remove another book's fallback. The 20-record cap per book and final
selection budget remain. Cache checks in the offline experiment runner also
include retrieval code and budgets, so old scores cannot be reused after those
inputs change.

The commit records focused regression checks and 32 of 32 saved recall anchors.
Those are dated validation records. This history update does not rerun them or
claim that the changes eliminate semantic assessment errors.

## October 12: Muse receives less unverified assessment prose

A sufficient assessment can select useful records while its explanation
attributes a detail to text that does not contain it. Commit
[`4cddb25`][writer-reason] changed Muse's `librarian_search` view of a
`sufficient` result to use a fixed explanation. The selected passages, IDs,
and strength stay available. Weak and absent evidence retain their reasons
and limitations. The underlying Librarian judgment still keeps its original
reason; this change applies to the result shown to Muse.

The same day's [`322af82`][stated-answers] tried an additional model step to
list answers explicitly stated by selected records. [`ae1bb4e`][answers-revert]
reverted that experiment. The current runtime has four Librarian skills and
no `stated-answers` skill or answer-list contract. The fixed sufficient-result
explanation survived the revert. Commit history establishes the addition and
removal; it does not establish a measured quality benefit or the full reason
for reverting it.

The [current writer view][writer-source] and [current skill assignments][skill-source]
show the retained behavior. Muse still needs to read the selected canonical
passages, and Provenance plus application checks still govern answer release.

## The current endpoint on October 14

The [current design][current-design] carries the same authority boundaries
through the later repairs. One reusable Librarian Agent has four selected
model tasks. Application code resolves books, carries accepted permission,
retrieves candidates, validates judgments, and restores canonical IDs.
Reader-confirmed saved progress can supply an accepted scope without private
inference. Inferred progress and exact-passage grants do not become saved
completed-chapter progress.

For answer retrieval, a plan uses exact reader spans and receives no candidate
text. Application code searches each granted book, applies part routing,
retains four records per planned query and two per context fallback, then
limits the merged pool to 20 per book. Without a plan, context retrieval keeps
the full pool budget. Assessment can recover omitted needs from original
reader text, but it does not start another search. The normal final selection
limit is five records across the search. Exact-passage grants assess their
fixed records instead of broadening the search.

These changes address specific losses between permission, retrieval,
assessment, and writing. The September checkpoint, October offline experiments,
and individual repair checks answer different questions. None is a fresh
end-to-end score for the October 14 runtime. The original limitations remain
part of the historical record; their presence here does not assert that each
one is still an open defect today.

[first-design]: https://github.com/DesmondChoy/linger/blob/205252c00872e2c3b8ec98383e55587393915553/docs/design/librarian-design.md
[corpus-design]: https://github.com/DesmondChoy/linger/blob/7935acaa1552daddc24214f1274daf96f3b310de/docs/design/librarian-design.md
[selection-design]: https://github.com/DesmondChoy/linger/blob/9a5d589/docs/design/librarian-design.md
[original-passages]: https://github.com/DesmondChoy/linger/blob/4abda38/docs/design/session-passage-design.md
[current-design]: ../../design/librarian-design.md
[passages]: ../../design/session-passage-design.md
[skills]: ../../agent-skills.md
[skills-issue]: https://github.com/DesmondChoy/linger/issues/46
[checkpoint]: ../../iteration-18-checkpoint.md
[decisions]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/decisions.tsv
[retrieval-design]: ../../../reports/librarian-fixes-2026-09-17/design-retrieval.md
[integration]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/design-integration.md
[boundary15]: ../../../synthetic-journal-evaluation/reports/librarian-fixes-2026-09-17/repair-15-boundary-design.md

[multi-book]: https://github.com/DesmondChoy/linger/commit/8c7bdba
[per-book]: https://github.com/DesmondChoy/linger/commit/7012886
[sequence-plan]: https://github.com/DesmondChoy/linger/commit/d72b87e
[part-routing]: https://github.com/DesmondChoy/linger/commit/d6b8e30
[assessment-repair]: https://github.com/DesmondChoy/linger/commit/3fa2c01
[short-labels]: https://github.com/DesmondChoy/linger/commit/544d648
[experiment3]: ../../evaluation/chapter-cue-experiment-3-2026-10-01.md
[experiment4]: ../../evaluation/retrieval-research-experiment-4-2026-10-01.md
[retention-fix]: https://github.com/DesmondChoy/linger/commit/5c4f4b4
[writer-reason]: https://github.com/DesmondChoy/linger/commit/4cddb25
[stated-answers]: https://github.com/DesmondChoy/linger/commit/322af82
[answers-revert]: https://github.com/DesmondChoy/linger/commit/ae1bb4e
[candidate-source]: https://github.com/DesmondChoy/linger/blob/9a5c074/src/linger/orchestration/book_evidence.py
[assessment-source]: https://github.com/DesmondChoy/linger/blob/9a5c074/src/linger/orchestration/evidence_strength.py
[hybrid-source]: https://github.com/DesmondChoy/linger/blob/9a5c074/apps/backend/hybrid_librarian.py
[writer-source]: https://github.com/DesmondChoy/linger/blob/9a5c074/src/linger/agents/muse/tools.py
[skill-source]: https://github.com/DesmondChoy/linger/blob/9a5c074/src/linger/agents/librarian/skills.py
