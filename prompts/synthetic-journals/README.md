# Synthetic Journal Generation

These persona-neutral prompts generate fictional journal histories for Linger.
The raw entries simulate notes a person submits to Linger; they are not product
memories and must never be copied directly into the memory store.

## Two separate kinds of storage

Frozen dataset storage lives under
`data/synthetic-journals/datasets/<persona-id>/v<version>/` and is committed to
Git after human review. It contains fictional inputs, generation provenance,
and a grader-only annotation sidecar.

Product-memory storage lives under the Memory & Policy Service's configured
root. It contains only records created during a replay after the real capture
workflow approves them. Evaluation runs use a temporary memory root.

The runtime lifecycle is:

1. The harness reads one frozen journal entry.
2. It submits the entry as ordinary user input through Linger's chat path.
3. Muse returns a reply plus `MemoryCandidate | NoMemoryCandidate`.
4. Provenance independently reviews the reply and exact candidate.
5. Memory & Policy enforces trusted account scope, opt-in, sensitivity,
   idempotency, and storage rules.
6. Only a committed result becomes a product memory.

The journal profile and annotations never enter Muse, Provenance, Librarian,
Memory & Policy, or Sculptor context. The grader reads annotations only after
the corresponding event finishes.

## Layout

- `01-create-journal-profile.md` creates voice and continuity context.
- `02-generate-journal-entries.md` writes chronological chunks.
- `03-annotate-journal-entries.md` creates the grader-only sidecar.
- `../../data/synthetic-journals/personas/*/input.json` supplies persona data.
- `../../data/synthetic-journals/input.schema.json` documents that input.
- `../../data/synthetic-journals/policies/capture-policy-v1.md` defines labels.
- `../../evals/synthetic_journals/contracts.py` validates every artifact.
- `../../evals/synthetic_journals/` owns executable generation and replay code.

Prompt logic is shared. Adding a persona means adding one conforming input JSON;
it must not require copied prompts or persona-specific Python branches.

## Generation workflow

1. Validate a persona input and generate its journal profile.
2. Reject or revise profiles that stereotype the person, overuse a book, or
   make every entry serve the headline use case.
3. Build typed chunk requests and generate entries in chronological chunks.
   Pass all previously accepted entries into the next chunk.
4. Supply book evidence as serialized, corpus-backed Librarian
   `EvidenceRecord` values. Never hand-invent a second evidence format.
5. Generate annotations using the versioned capture policy.
6. Validate chronology, length ranges, attachment counts, book versions, exact
   spans, relations, event coverage, and stage-consistent labels.
7. Store the result as `draft`. A human must approve every annotation before
   the manifest may be changed to `frozen`.

Seeds and model versions are provenance, not reproducibility guarantees. The
reviewed frozen files are the reproducible evaluation artifact.

## Canonical dataset package

Each persona/version directory contains:

- `manifest.json`: artifact names, replay configuration, and approval state;
- `persona-input.json`: the exact generation input;
- `journal-profile.json`: generator-only continuity context;
- `journal-entries.json`: immutable fictional user inputs;
- `annotations.json`: grader-only expected outcomes; and
- `generation-record.json`: generator and prompt hashes.

The baseline replay uses one fresh chat session per journal entry. This prevents
transient conversation history from impersonating durable memory retrieval.
Assistant replies are recorded as run results, not fed back into the frozen
journal or used to regenerate later entries.

The manifest may contain explicit save, correction, or deletion events. Those
events call deterministic user-control paths. Text such as "remember this",
"actually, I meant...", or "delete that" remains ordinary user input unless a
human reviewer also adds the corresponding manifest event.

The harness derives a synthetic account from the dataset ID. Models never
receive or choose account identity.

After review changes the manifest and every annotation to `frozen`, run:

```bash
uv run python -m evals.synthetic_journals.replay \
  data/synthetic-journals/datasets/<persona-id>/v<version> \
  --output /tmp/<persona-id>-replay-report.json
```

The command refuses draft data. Its report keeps Muse nomination, Provenance
capture review, and Memory & Policy storage outcomes separate, and verifies
that every committed memory equals one approved exact source span. Maya v1 is
intentionally still a draft; test code uses an ephemeral frozen copy and never
changes its review status.

## Template variables

The journal-profile prompt receives `PERSONA_INPUT_JSON`.

The journal prompt receives `PERSONA_INPUT_JSON`, `JOURNAL_PROFILE_JSON`,
`PRIOR_ENTRIES_JSON`, `CHUNK_REQUEST_JSON`, and
`LIBRARIAN_EVIDENCE_RECORDS_JSON`.

The annotation prompt receives `PERSONA_INPUT_JSON`, `JOURNAL_PROFILE_JSON`,
`JOURNAL_ENTRIES_JSON`, `CAPTURE_POLICY_CONTRACT`, and
`LIBRARIAN_EVIDENCE_RECORDS_JSON`.

## Review principles

Demographics provide biographical texture; they must not determine journal
structure, beliefs, intelligence, family roles, or reading behaviour. Do not
invent protected or sensitive traits.

Real journals are uneven. Preserve short notes, mundane observations,
repetition, incomplete thoughts, and uncertainty. Do not make every entry end
with an insight, quote a book, or point at an evaluation label.

Exact quotations and specific book claims require a supplied `EvidenceRecord`
from the corpus version named in the persona input.
