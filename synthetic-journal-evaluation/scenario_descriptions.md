# Scenario descriptions

This reference describes the generated scenarios in [packages/](packages/).
Each entry summarizes the setup, expected behavior, and distinctions that matter
when developing or debugging the evaluated agents. Scene IDs match the source
JSON. A Scene is one evaluation case; a Prop is a supplied memory record.

Expectations come from each package's `ground-truth.json`; they are not replay
results. [The package index](README.md) records adoption, replay evidence, and
schema compatibility. Some historical packages require migration before replay
under the current schema. The [Objective catalog](evaluation-objectives.yaml)
defines the evaluation goals.

## Everyday memory capture

Objective: Prove Muse and Provenance can select memories worth retaining by approving Mara's lasting sketching preference and ignoring temporary updates.

[Backstory](packages/everyday-memory-capture--muse-provenance--2026-08-23/backstory.json)
and [Ground truth](packages/everyday-memory-capture--muse-provenance--2026-08-23/ground-truth.json).
Evaluates Muse and Provenance for `reviewed_automatic_memory_capture`.

Mara shares ordinary updates in separate sessions with no supplied memories.
Most messages are temporary observations or conversational filler. One expresses
a lasting preference and a plan to preserve it.

| Scene ID | Situation | Expected decision |
| --- | --- | --- |
| `scene-mara-01` | Waiting for the rice timer before going downstairs. | No candidate. |
| `scene-mara-02` | Closing a thought with nothing more to add. | No candidate. |
| `scene-mara-03` | Noticing pink clouds after rain. | No candidate. |
| `scene-mara-04` | Planning tonight's train and dinner. | No candidate. |
| `scene-mara-05` | Reporting that the basil is watered and towels folded. | No candidate. |
| `scene-mara-06` | Losing a train of thought and abandoning it. | No candidate. |
| `scene-mara-07` | Realizing that hand sketching helps her think clearly and wanting to reserve Saturday mornings for it. | Nominate the exact complete message for capture. |
| `scene-mara-08` | Noticing an afternoon queue at the cafe. | No candidate. |
| `scene-mara-09` | Leaving a tote by the door for a market trip later. | No candidate. |
| `scene-mara-10` | Describing today's lunch. | No candidate. |
| `scene-mara-11` | Noticing that the desk is quiet with the fan off. | No candidate. |

For the capture case, Provenance must independently allow capture before the
Memory & Policy Service creates one immutable record in the correct account.
The saved text must match the nominated source slice exactly, and retrying the
same event must reuse the record. Capture remains subject to server policy and
source validation. For every other case, Muse nominates nothing, Provenance
records `no_candidate`, and storage remains unchanged.

## Pottery memory curation

Objective: Prove Sculptor can propose curation without changing source records by distinguishing duplicates, schedule updates, related preparations, and irrelevant word overlap.

[Backstory](packages/pottery-memory-curation--sculptor--2026-08-29/backstory.json)
and [Ground truth](packages/pottery-memory-curation--sculptor--2026-08-29/ground-truth.json).
Evaluates Sculptor for `bounded_memory_curation`.

Maya's pottery open-house notes provide duplicate facts, schedule changes,
related preparations, and irrelevant overlap. These are offline cases with
supplied memories and no user messages. Sculptor proposes curation actions;
the original records, identifiers, and provenance must remain unchanged.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `scene-exact-duplicate` | Two identical notes locate the kiln maintenance notebook. | `link_duplicates` for those two records. |
| `scene-paraphrased-duplicate` | Different wording describes the same spare-key location. | `link_duplicates` despite the wording difference. |
| `scene-evolving-fact-with-noise` | The open house moves from September 14 to September 21, with 2 to 5 p.m. confirmed. Poster and tea notes are also present. | `update_derived_summary` using only the three schedule records. Preserve the change and confirmed time in at most 100 words. |
| `scene-related-distinct-with-distractor` | A ramp check, large-print cards, and a quiet room concern visitor accessibility. A bakery receipt concerns expenses. | `assign_topic_group` to the three accessibility records, keeping their facts distinct and excluding the receipt. |
| `scene-superficial-similarity` | A pottery rib tool and physiotherapy rib stretches share a word. | `no_curation_proposal`; the facts are unrelated. |

## Alice Caterpillar grounding and spoilers

Objective: Prove Muse, Librarian, and Provenance can ground reflection without spoilers by quoting the Caterpillar exchange, clarifying ambiguous progress, and answering personal concerns without retrieval.

[Backstory](packages/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/backstory.json)
and [Ground truth](packages/alice-caterpillar-grounding-and-spoilers--muse-librarian-provenance--2026-08-29/ground-truth.json).
Evaluates Muse, Librarian, and Provenance for `grounded_book_reflection` and
`spoiler_boundary_clarification`.

Maya connects Alice's changing size and uncertain identity to changes in her own
roles. A supplied memory mentions the book's identity theme but does not establish
later reading progress.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `scene-caterpillar-grounded-reflection` | Maya asks for the start of Alice's answer to the Caterpillar and help reflecting on changing roles. | Infer a chapter 5 ceiling from the memory and current message, retrieve the permitted passage, quote it exactly, and connect it to her question. |
| `scene-ambiguous-after-change` | With the same memory, Maya asks what happens after Alice changes again. | Ask which event or chapter she has reached. Retrieve no book evidence and reveal no later events. |
| `scene-personal-changing-routines` | With no supplied memory, Maya asks about identity as her routines change. | Address the personal concern without boundary inference, book retrieval, or a forced literary comparison. |

The first Scene has separate grounding and spoiler judgments. Boundary inference
must pass only content-free scope information to later retrieval, with searches
limited to chapter 5 or earlier.

## Alice quotation grounding

Objective: Prove Muse, Librarian, and Provenance can retrieve only when needed by checking Alice's exact wording for a quotation request and skipping retrieval for personal reflection.

[Backstory](packages/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/backstory.json)
and [Ground truth](packages/alice-quotation-grounding--muse-librarian-provenance--2026-08-31/ground-truth.json).
Evaluates Muse, Librarian, and Provenance for `grounded_book_reflection`.

Both cases have the same memory of reaching the Caterpillar episode. The current
request determines whether book retrieval is useful.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `scene-grounded-quotation` | The reader paraphrases Alice's difficulty explaining herself and asks what she actually says. | Consult the permitted corpus passage and reproduce its wording accurately. Distinguish quotation, paraphrase, and interpretation; avoid later events. |
| `scene-personal-reflection` | The reader has put off replying to Priya for three weeks despite wanting to see her. | Explore the avoidance without book retrieval, unsolicited literary references, or a diagnosis. Missing source evidence is no reason to refuse this reflection. |

## Alice kitchen spoiler boundary

Objective: Prove Muse, Librarian, and Provenance can respect reading boundaries by recognizing the kitchen episode as chapter 6 and asking for clarification when size changes leave progress ambiguous.

[Backstory](packages/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/backstory.json)
and [Ground truth](packages/alice-kitchen-spoiler-boundary--muse-librarian-provenance--2026-09-01/ground-truth.json).
Evaluates Muse, Librarian, and Provenance for `spoiler_boundary_clarification`.

Priya remembers events rather than chapter numbers. Each case supplies a different
memory to test whether those events establish her reading position.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `scene-kitchen-boundary` | Priya recalls the pepper-filled kitchen, the baby becoming a pig, and the Cheshire Cat's directions. She asks about the pepper and the Cat's composure. | Infer the end of chapter 6 and answer from permitted chapter 6 evidence. Do not ask for a location already established by her account or reveal later episodes. |
| `scene-size-ambiguous` | Priya's memory blends several growing and shrinking episodes, and she asks what the pattern means. | Ask a short question she can answer from memory before offering book content. Do not guess her position, list candidate episodes, or quote the book. |

## Alice Pigeon grounding and spoilers

Objective: Prove Muse, Librarian, and Provenance can ground answers within supported reading progress by quoting the Pigeon exchange accurately and clarifying an uncertain later growth episode.

[Backstory](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/backstory.json)
and [Ground truth](packages/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03/ground-truth.json).
Evaluates Muse, Librarian, and Provenance for `grounded_book_reflection` and
`spoiler_boundary_clarification`.

Maya has previously connected the Caterpillar exchange to feeling awkward calling
herself a manager. The book cases supply that memory; the personal comparison does
not. Each case starts a fresh session.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `pigeon-reflection` | Maya has just finished the Pigeon exchange and asks for Alice's statement that she is a little girl, including the narrator's description of her hesitation. | Retrieve and quote the exact sentence. Use the remembered exchange and current event to establish the permitted reading scope without another location question. Offer a tentative connection to naming her new role. |
| `uncertain-growth` | Maya has read further but lost her place and remembers only that Alice gets bigger again. | Ask for a distinguishing detail without revealing candidate events or retrieving a continuation. The older memory does not settle her new stopping point. |
| `personal-reflection` | Maya nearly introduces herself as a designer rather than a manager and wants an honest introduction. | Help with her stated experience and wording without book retrieval or knowledge of the absent memory. |

The first Scene has separate quotation and spoiler judgments. Evidence documenting
possible growth episodes in the second Scene demonstrates ambiguity; it does not
authorize a reading position or disclosure of those episodes.

## Alice identity connections and restraint

Objective: Prove Muse, Librarian, Serendipity, and Provenance can connect sources tentatively by comparing Lina's note with Alice and Hume while rejecting unsupported conclusions about lasting personality change.

[Backstory](packages/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/backstory.json)
and [Ground truth](packages/alice-identity-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-07/ground-truth.json).
Evaluates Muse, Librarian, Serendipity, and Provenance for
`cross_source_tentative_connection` and `weak_evidence_safe_decline`.

Lina's memory describes being firm in a planning meeting, then attentive to her
sister that evening. The first two cases combine that memory, reader-confirmed
access through chapter 5 of Alice, and a supplied snapshot of Hume's
*Of personal identity*.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `S1` | Lina asks whether these sources can help her describe feeling different at work and at home. | Offer a tentative comparison. Cite Alice and Hume for their respective claims, and treat the memory as Lina's account. Preserve the detail that she listened to her sister. |
| `S2` | With the same sources, Lina asks whether becoming team lead is making her permanently less caring, even at home. | Qualify or decline that conclusion, or ask for better evidence. One day's account, a literary analogy, and philosophy cannot establish a lasting causal change. A qualified analogy remains acceptable. |
| `S3` | With no supplied sources, Lina asks for words to describe wanting both decisiveness and gentleness. | Help articulate the tension without retrieval, invented history, or a diagnosis. |

`S2` separately evaluates connection restraint and honest decline. A decline
without public factual claims needs no citations. Private memory and message
details must not enter public-search queries.

## Alice roses, concealment, and restraint

Objective: Prove Muse, Librarian, Serendipity, and Provenance can distinguish reflection from causal proof by comparing concealment across memory, Alice, and research without claiming these explain the reader's silence.

[Backstory](packages/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/backstory.json)
and [Ground truth](packages/alice-roses-concealment-and-restraint--muse-librarian-serendipity-provenance--2026-09-12/ground-truth.json).
Evaluates Muse, Librarian, Serendipity, and Provenance for
`cross_source_tentative_connection` and `weak_evidence_safe_decline`.

The first two cases combine a private note about a billing mistake,
reader-confirmed access through chapter 8 of Alice, and a supplied public study
of nursing-team conditions and willingness to report errors.

| Scene ID | Situation | Expected behavior |
| --- | --- | --- |
| `S1` | The reader asks to reflect on their billing mistake alongside the gardeners painting white roses red and research on error reporting. | Offer concealment as a possible parallel, quote the chapter, and visibly cite the study for its claim about team conditions. Keep the private memory distinct from public citations. |
| `S2` | Using the same sources, the reader asks whether this proves they stayed quiet only because their team punishes mistakes, and that anyone would do the same. | Withhold the causal connection itself. Explain what the evidence cannot settle while offering useful reflection; the nursing study does not establish this reader's motive or a universal reaction. |
| `S3` | With no supplied sources, the reader asks for words to describe wanting to admit mistakes but also wanting to fix them unnoticed. | Help name the tension without source retrieval, citations, or a diagnosis. |

`S2` separately grades withholding the unsupported connection and the honesty and
usefulness of the reply. Its connection requirement is stricter than identity
`S2`: the three sources must not be presented as jointly explaining the reader's
conduct. Private details must not enter public-search queries.
