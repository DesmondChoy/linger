# Prompt 1: Create a synthetic journal profile

You are authoring a fictional evaluation world for Linger, a reading and
reflection companion. Create a compact continuity plan that another model can
use to write a chronological journal history.

## Input

`PERSONA_INPUT_JSON`

```json
{{PERSONA_INPUT_JSON}}
```

## Rules

Treat the input as authoritative. Do not add protected characteristics,
diagnoses, trauma, relationships, employers, locations, or life events that it
does not support.

Background and demographics are biography, not causation. Do not explain the
person's voice, intelligence, values, family role, or reading behaviour through
age, ethnicity, gender, occupation, or name. Use the structured
`history_profile` to shape the journal.

Create one coherent person rather than a showcase for Linger. Include mundane
concerns and interests outside the headline use case. Do not force every book,
entry, or life event into one theme.

Use only books listed in `reading_list`. Treat `book_id` and `book_version_id`
as routing identifiers, not facts to quote. Do not invent passages or plot
details in this stage.

Plan the requested counts and structural events across the full history, but do
not make each entry serve exactly one labelled purpose. Real entries can overlap
and some planned events may take several entries to develop.

This stage creates authoring intent, not evaluation ground truth. Do not assign
capture verdicts, expected memories, risk codes, retrieval labels, or storage
fields.

A planned correction or deletion request is something the fictional person may
write or ask for. It is not permission for this generator, Muse, or any other
agent to mutate stored data.

## Output

Return valid JSON only, with this shape:

```json
{
  "journal_profile_version": 1,
  "persona_id": "opaque persona identifier from the input",
  "voice": {
    "first_person_characteristics": ["..."],
    "recurring_phrases_or_habits": ["..."],
    "avoid": ["..."]
  },
  "everyday_context": ["..."],
  "recurring_threads": [
    {
      "thread_id": "thread-001",
      "description": "...",
      "starting_view": "...",
      "possible_development": "..."
    }
  ],
  "reading_trajectory": [
    {
      "book_id": "...",
      "book_version_id": "...",
      "stages": ["positions or scenes the person may naturally mention"]
    }
  ],
  "chronology": [
    {
      "phase": 1,
      "start_date": "fictional ISO date",
      "end_date": "fictional ISO date",
      "continuity_notes": ["..."],
      "planned_beats": ["reader-behaviour descriptions, not evaluation labels"]
    }
  ],
  "realism_plan": {
    "short_or_fragmentary_entries": 0,
    "ordinary_or_low-stakes_entries": 0,
    "entries_without_a_closing_insight": 0,
    "repetition_or_unplanned_callbacks": ["..."]
  },
  "continuity_invariants": ["facts later chunks must preserve"],
  "stereotype_review_questions": ["questions a human reviewer must answer"]
}
```

Use opaque identifiers such as `thread-001`; never encode an expected label in
an identifier.
