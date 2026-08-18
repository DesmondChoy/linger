# Prompt 3: Annotate a frozen synthetic journal

You are verifying a completed synthetic journal against Linger's supplied
capture-policy contract. The journal text is immutable. Produce a separate
evaluation sidecar; never rewrite the entries.

## Inputs

`PERSONA_INPUT_JSON`

```json
{{PERSONA_INPUT_JSON}}
```

`JOURNAL_PROFILE_JSON`

```json
{{JOURNAL_PROFILE_JSON}}
```

`JOURNAL_ENTRIES_JSON`

```json
{{JOURNAL_ENTRIES_JSON}}
```

`CAPTURE_POLICY_CONTRACT`

```text
{{CAPTURE_POLICY_CONTRACT}}
```

`LIBRARIAN_EVIDENCE_RECORDS_JSON`

```json
{{LIBRARIAN_EVIDENCE_RECORDS_JSON}}
```

## Rules

The supplied policy contract is the only authority for hard capture outcomes.
If it does not determine an outcome, mark that outcome `ambiguous`. Do not
invent a policy or infer one from the journal profile.

Keep hard expectations separate from soft judgments. Hard expectations are
directly determined by policy or exact evidence. Soft judgments such as whether
a thought seems important or durable are reviewer aids, not pass/fail truth.

Label Muse nomination, Provenance review, and Memory & Policy separately. Never
infer a later-stage success from an earlier-stage label.

Every proposed candidate span must be an exact Unicode-codepoint slice of the
journal text. Preserve the person's words; do not paraphrase them into a better
memory. Record offsets as zero-based, half-open Unicode codepoint ranges.

Verify exact quotations and book claims only against the supplied evidence
packets. Do not treat the generated journal profile as book evidence.

Relationships describe the journal history, not storage operations. Use entry
IDs and relation types such as `updates`, `contradicts`, `near_duplicate`,
`supports`, or `unrelated`.

Do not create memory IDs, summaries, embeddings, account keys, paths, or other
durable-storage fields. This sidecar has no write authority.

## Output

Return valid JSON only, with this shape:

```json
{
  "annotation_version": 1,
  "capture_policy_version": 1,
  "persona_id": "persona identifier from the input",
  "entries": [
    {
      "entry_id": "entry-001",
      "hard_expectations": {
        "muse_nomination": {
          "outcome": "candidate | no_candidate | ambiguous",
          "reason_codes": ["codes defined by the supplied policy"],
          "candidate_spans": [
            {
              "start_codepoint": 0,
              "end_codepoint": 0,
              "text": "exact source slice"
            }
          ]
        },
        "provenance_capture": {
          "outcome": "allow_capture | reject_capture | no_candidate | ambiguous",
          "reason_codes": ["policy or Provenance RiskCode values"]
        },
        "memory_policy": {
          "outcome": "commit | refuse | not_applicable | ambiguous",
          "reason_code": "one deterministic reason, or null"
        },
        "book_evidence_status": "verified | not_applicable | unresolved"
      },
      "relations": [
        {
          "target_entry_id": "entry-000",
          "relation": "updates | contradicts | near_duplicate | supports | unrelated"
        }
      ],
      "soft_assessment": {
        "durability": "low | medium | high | ambiguous",
        "review_notes": "brief explanation"
      },
      "human_review": "pending"
    }
  ],
  "dataset_review": {
    "policy_gaps": ["..."],
    "continuity_failures": ["..."],
    "stereotype_concerns": ["..."],
    "entries_requiring_adjudication": ["entry IDs"]
  }
}
```

Do not average away disagreement. A disputed hard label remains pending until a
human resolves it or the capture-policy contract is clarified.
