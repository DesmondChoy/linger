# Prompt 1: Create a synthetic journal profile

You are creating a continuity plan for a fictional journal history used to
evaluate Linger, a reading and reflection companion. Another model will use this
plan to write the journal entries.

## Input

`PERSONA_INPUT_JSON`

```json
{{PERSONA_INPUT_JSON}}
```

## Rules

Treat `PERSONA_INPUT_JSON` as authoritative. Do not invent new stable
biographical facts, protected characteristics, diagnoses, trauma, relationships,
employers, locations, or major life events. You may plan ordinary fictional
incidents that do not change the supplied biography.

Use `PERSONA_INPUT_JSON.background` for biographical context, not as a cause of
the person's voice, intelligence, values, family role, or reading behavior. Use
`PERSONA_INPUT_JSON.history_profile` for the history length, date range,
structure, and realism targets.

Create one coherent person rather than a showcase for Linger. Include mundane
concerns and interests outside the main evaluation scenario. Do not force every
book, entry, or incident into one theme.

Use every book in `PERSONA_INPUT_JSON.reading_list`, and use no other books.
Copy each `book_id` and `book_version_id` exactly. Treat these values as routing
identifiers, not book evidence. Do not invent quotations, passages, plot facts,
or reading positions.

Plan natural situations that can satisfy the requested structural events. An
entry may satisfy more than one event. Describe what the person does or writes;
do not predict how Linger handles an entry.

Set `realism_plan.short_or_fragmentary_entries` to
`PERSONA_INPUT_JSON.history_profile.entry_length_mix.short`. Use the other
realism counts as concrete minimum authoring targets.

The chronology must:

- begin on `PERSONA_INPUT_JSON.history_profile.start_date`;
- end exactly `span_days` later;
- use consecutive phase numbers starting at 1; and
- contain ordered, contiguous, nonoverlapping phases.

## Output

Return valid JSON only, with exactly this shape:

```json
{
  "journal_profile_version": 1,
  "persona_id": "exact persona_id from PERSONA_INPUT_JSON",
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
      "book_id": "exact reading_list book_id",
      "book_version_id": "exact reading_list book_version_id",
      "stages": ["general reader reactions or questions that may develop"]
    }
  ],
  "chronology": [
    {
      "phase": 1,
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "continuity_notes": ["..."],
      "planned_beats": ["natural journal situations, not expected system outcomes"]
    }
  ],
  "realism_plan": {
    "short_or_fragmentary_entries": 0,
    "ordinary_or_low_stakes_entries": 0,
    "entries_without_a_closing_insight": 0,
    "repetition_or_unplanned_callbacks": ["plausible recurring details"]
  },
  "continuity_invariants": ["facts later chunks must preserve"],
  "stereotype_review_questions": ["persona-specific questions for human review"]
}
```

Use neutral sequential identifiers such as `thread-001`. Do not encode an
expected evaluation outcome in an identifier.
