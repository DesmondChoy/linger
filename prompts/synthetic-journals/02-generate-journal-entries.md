# Prompt 2: Generate chronological journal entries

You are writing the next chronological chunk of a fictional person's private
journal notes sent to Linger. Write only what that person could have submitted,
plus the metadata in the output schema.

## Inputs

`PERSONA_INPUT_JSON`

```json
{{PERSONA_INPUT_JSON}}
```

`JOURNAL_PROFILE_JSON`

```json
{{JOURNAL_PROFILE_JSON}}
```

`PRIOR_ENTRIES_JSON`

```json
{{PRIOR_ENTRIES_JSON}}
```

`CHUNK_REQUEST_JSON`

```json
{{CHUNK_REQUEST_JSON}}
```

`LIBRARIAN_EVIDENCE_RECORDS_JSON`

```json
{{LIBRARIAN_EVIDENCE_RECORDS_JSON}}
```

## Rules

Follow `JOURNAL_PROFILE_JSON` and continue from `PRIOR_ENTRIES_JSON` without
summarizing prior entries. Generate exactly the sequence numbers requested by
`CHUNK_REQUEST_JSON`, in order, with no duplicates.

Treat `CHUNK_REQUEST_JSON` as authoritative for this chunk. Every timestamp must
fall within its inclusive timestamp window and include a UTC offset. Match its
`length_targets`, `attachment_target`, and `event_targets` exactly. One entry may
satisfy more than one event target.

Use `PERSONA_INPUT_JSON.history_profile.entry_word_ranges` as inclusive hard
bounds. An entry outside all three ranges is invalid.

Write in first person. Preserve the established voice without turning
demographics into stereotypes. Do not mention that the person is fictional, an
evaluation persona, or using a test system.

Make the entries uneven and credible. Vary length, confidence, detail, and
finish. Some entries may be mundane, repetitive, unresolved, or fragmentary.
Do not make every entry end with an insight or lesson.

Satisfy the requested situations naturally. Do not announce an entry's
significance, mention dataset categories, or explain why an entry was included.
A correction, deletion request, or reconnection request must read as something
the person naturally writes, not as generator commentary.

Use only books in `PERSONA_INPUT_JSON.reading_list`. In an evidence record,
`work_id` corresponds to the reading-list `book_id`; `book_version_id` must also
match. An exact quotation or specific book claim requires a matching record in
`LIBRARIAN_EVIDENCE_RECORDS_JSON`. Without matching evidence, use only a general
personal reaction or omit the detail. Never invent a quotation, chapter fact, or
reading position.

Preserve reading positions exactly as the person expresses them. Do not convert
a vague phrase such as "somewhere near the middle" into a chapter number.

Create exactly `CHUNK_REQUEST_JSON.attachment_target` synthetic attachment
descriptions. Follow `PERSONA_INPUT_JSON.history_profile.attachments`. Describe
only directly observable fictional content; do not infer identity, relationship,
health, emotion, ownership, or symbolism.

The `text` field must contain only the person's journal words, without
annotations, summaries, tags, evaluation terminology, or metadata. Return
exactly the fields shown.

## Output

Return valid JSON only, with exactly this shape. Code assigns stable entry and
attachment identifiers after validation.

```json
{
  "entries": [
    {
      "sequence": 1,
      "timestamp": "YYYY-MM-DDTHH:MM:SS+00:00",
      "text": "verbatim journal text",
      "attachments": [
        {
          "kind": "image",
          "description": "neutral description of synthetic visible content"
        }
      ],
      "book_contexts": [
        {
          "book_id": "exact reading_list book_id",
          "book_version_id": "exact reading_list book_version_id",
          "declared_position": "position exactly as written in text, or null"
        }
      ]
    }
  ]
}
```

Include a `book_contexts` item for each listed book mentioned in the entry and
none for books not mentioned. Use `[]` for empty attachments and book contexts.
