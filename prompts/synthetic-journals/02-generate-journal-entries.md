# Prompt 2: Generate chronological journal entries

You are writing the next chronological chunk of a fictional person's private
journal notes sent to Linger. Write only what that person could have submitted,
plus minimal ordering and context metadata.

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

Follow the journal profile and continue from prior entries without summarising
them. Generate exactly the sequences requested by `CHUNK_REQUEST_JSON`.
Respect its timestamp window and length targets. Use the persona input's
`entry_word_ranges` as the exact definition of short, medium, and long.

Write in first person. Preserve the person's established voice without turning
demographics into stereotypes. Do not mention that the person is fictional, an
evaluation persona, or using a test system.

Make the entries uneven and credible. Vary length, confidence, detail, and
finish. Some entries may be short, mundane, repetitive, unresolved, or
fragmentary. Do not make every entry arrive at an insight or end with a neat
lesson.

The fixed event counts in `history_profile` apply across the entire history, not
as a checklist for this chunk. Do not visibly write toward capture, deletion,
retrieval, safety, or other evaluation labels.

Use books only when natural. An exact quotation or specific book claim must be
supported by `LIBRARIAN_EVIDENCE_RECORDS_JSON`. If the relevant evidence is
absent, refer only to the person's general reaction or omit the detail. Never
invent a quotation, chapter fact, or reading position.

When a position is mentioned, preserve how the person would say it. A vague
reader may say "around the tea party"; do not silently rewrite that as a chapter
number.

Attachment descriptions must be neutral observations of visible content. Do
not pre-interpret identity, relationship, health, emotion, or symbolism.

The journal text is immutable source material. Do not add memory candidates,
summaries, topic tags, evaluation labels, risk codes, span offsets, hashes, or
storage fields.

## Output

Return valid JSON only, with this shape:

```json
{
  "journal_dataset_version": 1,
  "persona_id": "persona identifier from the input",
  "entries": [
    {
      "entry_id": "entry-001",
      "sequence": 1,
      "timestamp": "fictional ISO 8601 datetime",
      "text": "verbatim journal text",
      "attachments": [
        {
          "attachment_id": "attachment-001",
          "kind": "image",
          "description": "neutral visible description"
        }
      ],
      "book_contexts": [
        {
          "book_id": "corpus-bound identifier",
          "book_version_id": "corpus version",
          "declared_position": "the position exactly as expressed in the entry, or null"
        }
      ]
    }
  ]
}
```

Use opaque sequential entry and attachment identifiers. Empty attachments and
book contexts are `[]`, never omitted.
