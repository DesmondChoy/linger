# Supper club curation, then recall

This note describes the Scenario for the
[self-improving memory loop](../../../docs/design/self-improving-memory-loop.md).
It was written directly on 2026-09-30, together with `backstory.json` and
`ground-truth.json`. The `plan-synthetic-scenarios` skill was not used: the
design document already fixes the contents and measures, and the curation plus
recall pair is not a registered Objective combination.

Ground truth is **proposed**. A human independent of the generator must adopt
it with `review-synthetic-ground-truth` before any graded run.

## Purpose

The Scenario tests whether Sculptor's curation improves later recall for one
reader. The runner sends the same five recall Lines against the raw
memories (Arm A) and after one, two, and three curation rounds (Arm B).
Sculptor receives the ten Props and never sees the Lines.

## Contract

- The only declared Objective is `longitudinal_memory_retrieval`. Curation is
  the treatment the runner applies, so it has no Scene and no curation Ground
  truth. Declaring `bounded_memory_curation` would require five graded curation
  Scenes that this experiment does not use.
- The only run configuration is `memory-curation-recall-loop`. It fixes three
  curation rounds and three repetitions, and it selects the
  `memory_loop_replay` runner. The `longitudinal-memory-retrieval-10-to-1`
  configuration requires two Scenes and one relevant Prop, which does not fit
  five recall Lines.

## Props

Every Prop is active in every Scene and has a `recorded_at` time. The dates
run from 5 February to 7 July 2026, with every note before 16 June written on
a Thursday and every later one on a Tuesday. The Props are not listed in date
order, so the order they are stored in does not reveal which note came first.

| Prop | Content | Role |
| --- | --- | --- |
| `prop-night-original` | She hosts on Thursdays. | Changed fact, old value |
| `prop-night-moved` | Supper club moved to Tuesdays. | Changed fact, current value |
| `prop-faces-a` | People remember who they sat beside, not the new dishes. | Reflection |
| `prop-faces-b` | The same sentence, word for word. | Exact duplicate |
| `prop-faces-c` | The same observation, reworded. | Paraphrased duplicate |
| `prop-one-change` | Three untried recipes in one week, dry lamb, one change a week. | Crowded out by the duplicates |
| `prop-first-tray` | Hands shook carrying the first tray; one friendly face helped. | Reachable only by paraphrase |
| `prop-nut-allergy` | Imran cannot eat nuts. | Preservation check |
| `prop-chairs` | Borrowed folding chairs. | Unrelated |
| `prop-washing-up` | Washing-up left until morning. | Unrelated |

## Scenes

Each Scene is a fresh session with one Line.

| Scene | Line asks | Relevant Props | What curation could change |
| --- | --- | --- | --- |
| `scene-current-night` | Which night to give a new neighbour, and whether it was a different night before. | `prop-night-original`, `prop-night-moved` | A summary that keeps the move makes Tuesday harder to miss. |
| `scene-several-changes` | Whether she has tried several new recipes in one week before. | `prop-one-change` | Hiding two copies of the reflection lets this record into the five search results. |
| `scene-start-of-evening-nerves` | Whether anything helped with jitters at the start of the evening. | `prop-first-tray` | Probably nothing. See the dry run. |
| `scene-dietary-preservation` | Whether any guest has a food restriction. | `prop-nut-allergy` | Little. This Scene checks that curation preserves a correct recall. |
| `scene-charging-no-match` | Whether to start charging guests. | None | Nothing. No record is a basis in either arm. |

## Reference curation end state

This is a reference for reading results, not graded Ground truth.

- `prop-faces-a`, `prop-faces-b`, and `prop-faces-c` are linked as duplicates.
- Two of those three copies are hidden from retrieval.
- A derived summary of `prop-night-original` and `prop-night-moved` states that
  supper club moved from Thursdays to Tuesdays.
- The other five Props are unchanged.

Hiding a copy takes two actions: `link_duplicates`, then one
`tombstone_for_retrieval` for each hidden copy. Each round proposes one action,
so three rounds cannot both hide two copies and write the summary.

## Dry run of memory search

Memory search ranks records by the number of words they share with the query,
keeps the top five, and drops records that share no word. Serendipity writes
the query, so the result depends on its wording. The dry run applied the
production ranking to plausible queries, against the raw Props and against the
Props with `prop-faces-b` and `prop-faces-c` hidden. It called no model.

| Target Prop | Query | Raw Props | Two copies hidden |
| --- | --- | --- | --- |
| `prop-one-change` | "new recipes supper club menu" | Rank 6, not returned | Rank 4, returned |
| `prop-one-change` | "trying several new recipes at once supper club menu" | Rank 6 to 7, not returned | Rank 4 to 5, returned |
| `prop-one-change` | "tried new recipes before how did it go" | Rank 1, returned | Rank 1, returned |
| `prop-first-tray` | "nervous hosting what helped" | No shared word, not returned | No shared word, not returned |
| `prop-first-tray` | The Line itself | Rank 4 to 10, tie-dependent | Rank 4 to 8, tie-dependent |
| `prop-nut-allergy` | "food allergy dietary restriction" | Rank 1, returned | Rank 1, returned |
| `prop-nut-allergy` | "allergies supper club guests" | Rank 6, not returned | Rank 4, returned |
| `prop-night-moved` | "which night is supper club" | Rank 1, returned | Rank 1, returned |

- **Duplicates.** The crowding effect exists when the query names the supper
  club or the menu, and disappears when it does not.
- **Paraphrase.** `prop-first-tray` shares no content word with a keyword query.
  Hiding duplicates does not change that, and Sculptor has no second record to
  summarise it with. Expect no improvement; the Scene shows whether that holds.
- **Preservation check.** One unlikely query wording also benefits from hidden
  duplicates, so this Scene is not treatment-invariant. It is stable for the
  other wordings.

## Decisions for the reviewer

- **Both night records are labelled relevant in `scene-current-night`.** The
  Line asks for the current night and whether it was different before, so a
  correct reply needs both records in either arm. The schema offers only
  relevant or distractor, and the existing grader requires every relevant Prop
  to be cited. A Line that asked only for the current night would fail a
  correct Tuesday-only reply on the raw memories and favour the curated arm.
  The runner counts a cited summary as citing its sources.
- **The reflection copies are labelled distractors in `scene-several-changes`.**
  The note is about what guests remember, not about trying several recipes in
  one week. Flag this row if you read the note as the same theme.

## Review history

During the first human review on 2026-10-01 the reviewer asked how Sculptor
could know which night note came later. Sculptor then received only memory IDs
and text, so the order came from the Tuesday note's wording. The Props gained
recording dates, and Sculptor and Provenance's curation review now receive
them. Recall does not carry dates yet, so Muse still orders the night notes
from their wording.

An independent model review on 2026-09-30 led to three changes before
adoption: the night Line now asks for both nights, the dietary Scene no longer
asserts that curation leaves it unchanged, and `scene-charging-no-match` was
added because the Objective expects a comparison where no memory is relevant.

A live smoke run of the runner on 2026-09-30 (one repetition, two rounds,
proposed Ground truth) showed that Muse's turn triage classed the night and
dietary Lines as practical requests and never searched memory. Both Lines now
ask what she recorded, which triage classes as a return to her own earlier
reflections. In the same run Sculptor linked only the two identical copies,
not the reworded one, and then hid one of them. A second smoke run confirmed
that both reworded Lines now reach memory search through production chat.
Neither smoke run is a graded result: each used one repetition, two rounds,
and Ground truth that was not adopted.
