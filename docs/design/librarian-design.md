# Librarian subsystem design

Status: **Five registered corpora with bounded chapter, reading-unit, and exact-passage retrieval**

Source snapshot: 14 October 2026, `librarian-attempts` at `cac9477`, based on
`main` at `9a5c074`. This document describes the current runtime. The
[design history](../reports/librarian-experiments-2026-09-24/design-history.md)
records the experiments, reversions, and reasons for earlier changes.

Historical measurements below retain their original dates and scope. They do
not evaluate every aspect of the current implementation.

This document defines the retrieval-neutral book corpus and the typed boundary
of the Librarian implementation. It elaborates on the Librarian
responsibilities and safeguards in [`../specification.md`](../specification.md).

## Implementation scope

The runtime registry and default access list contain Alice, Animal Farm,
Pinocchio, Frederick Douglass's Narrative, and The Story of My Life. Routing
resolves reviewed book identities and catalogue cues, with active session
selection available for indirect book follow-ups. Private inference supports
memory-backed chapter ceilings and session-supported exact paragraphs.
Explicit completed-chapter progress persists per account and work, and routing
can reuse it after identifying the book. Application code validates every
grant before a separate evidence search and deterministic release checks.

The current evidence path plans exact reader spans before retrieval. It keeps
four candidates per planned query in matching books and two per original-text
fallback query in every allowed book, then caps the merged pool at twenty per
book. The assessor receives full canonical records under temporary `E1`, `E2`
labels and selects at most five records across the search. Application code
restores canonical IDs and checks requested-part coverage before release.
Muse receives a fixed reason for `sufficient` results. Serendipity and the
recorded Librarian assessment retain the model's reason.

The corpus lifecycle prepares five books, including section-based works.
Preparation does not register a book for runtime use. The versioned-memory
design remains deferred and independent of Librarian. Beads owns delivery
status; `bd ready` and `bd list --status open` show current work.

The historical Alice benchmark selected spoiler-bounded BM25 plus semantic retrieval,
reciprocal-rank fusion, overlap deduplication, and local cross-encoder reranking.
All five configurations passed the zero-forbidden-exposure and exact-resolution
gates. The selected retrieval path reached 91.7% evidence recall and 82.6%
candidate precision; the latter is diagnostic because the Librarian judge still
filters candidates before Muse receives final evidence. The live 12-case
Librarian → Muse → Provenance release evaluation then reached 91.7% final
evidence recall, 100% citation precision, and zero spoiler exposure.

## Agent and assigned skills

The Librarian subsystem contains one reusable production PydanticAI object,
`librarian_agent`. Its explicit assignment in
[`skills.py`](../../src/linger/agents/librarian/skills.py) contains four skills:

| Skill | Contract | Current consumer |
|---|---|---|
| [Boundary inference](../../src/linger/agents/librarian/skills/boundary-inference/SKILL.md) | `LibrarianBoundaryInferenceInput` → `LibrarianBoundaryDecision` | Production book routing and synthetic book replay call private inference when explicit progress is unavailable. |
| [Event identification](../../src/linger/agents/librarian/skills/event-identification/SKILL.md) | `LibrarianEventIdentificationInput` → `LibrarianEventIdentification` | An independent run checks the stopping occurrence before the application accepts a proposed chapter grant. |
| [Book request](../../src/linger/agents/librarian/skills/book-request/SKILL.md) | `LibrarianBookRequestInput` → `BookRequestPlan` | Muse and Serendipity supply reader context without candidate passages to identify the requested book parts. |
| [Evidence assessment](../../src/linger/agents/librarian/skills/evidence-assessment/SKILL.md) | `LibrarianEvidenceStrengthInput` → `BookEvidenceAssessment` | A frozen request plan and scoped canonical evidence support selection and answerability judgment. Application checks return `EvidenceStrengthDecision`. |

Application code selects one skill before each model run. All runs use the
same Agent object with shared trust rules, task-specific instructions, and a
per-run output schema. They receive no tools or retained conversation history.
Original reader statements are explicit boundary-inference input data.
Sharing the object does not combine these tasks into one model call.

Work resolution, scoped search, fusion, deduplication, reranking, canonical
resolution, and permission validation remain application operations. They are
not additional model skills. See the
[runtime architecture](../agent-skills.md) and
[role README](../../src/linger/agents/librarian/README.md) for instructions,
fingerprints, and ownership.

## 1. Purpose and scope

The subsystem has two deliberately separate flows:

1. **Offline corpus preparation** converts a verified source book into
   canonical, human-readable Markdown chapters and a derived metadata-only
   catalogue.
2. **Online retrieval** uses a request-scoped reading boundary to either ask one
   focused clarification or inspect only eligible reading units and return a typed
   evidence result to Muse.

The five prepared corpora are registered for runtime use. Chapter corpora use
chapter ceilings; section corpora preserve part identity and allow exact unit
selectors. The walkthrough and historical evaluation below use Alice, Project
Gutenberg ebook 11. Direct canonical reads remain the benchmark control; the
measured production path uses bounded BM25 and local embeddings, reciprocal-rank fusion,
overlap deduplication, and a local cross-encoder reranker before the independent
Librarian evidence-strength decision.

### 1.1 Responsibilities

Librarian may:

- privately search all numbered chapters in an authorised work's main part to locate reader-known events;
- propose a request-scoped candidate ceiling with confidence and supporting locations;
- inspect compact metadata for chapters inside the current request's boundary;
- receive canonical passages selected by application retrieval;
- use the implemented keyword, semantic, and hybrid retrieval services;
- judge whether the retrieved evidence is sufficient, weak, or absent; and
- return exact source evidence and resolvable locations to Muse.

Librarian may not:

- grant, persist, or widen the user's reading boundary; application code must validate its candidate;
- expose metadata or text beyond the validated request scope;
- treat generated routing metadata as citable evidence;
- invent, rewrite, or silently truncate source evidence;
- save, modify, or delete memories;
- draft the final user-facing response; or
- bypass Provenance or deterministic validation.

## 2. System overview

### 2.1 Offline corpus flow

```text
Immutable Gutenberg source + download metadata
                    ↓
Verify source hash and book structure
                    ↓
Extract natural chapters or sections deterministically
                    ↓
Canonical Markdown chapters or sections
(exact layout + compact JSON front matter)
                    ↓
Derived metadata-only catalogue
                    ↓
Derived evaluation indexes
(BM25 paragraph windows and embeddings)
```

The immutable text file remains the upstream source. The checked-in Markdown
chapters are the canonical retrieval corpus. The catalogue and any future
search indexes are disposable projections that must be regenerable from those
chapters.

### 2.2 Online retrieval flow

```text
Original reader message + earlier reader statements
                    ↓
Application resolves the work from a declaration or Muse's librarian_route
                    ├─ unresolved identity → focused clarification
                    ↓
Validate current, carried, or saved permission for that work and part
        ├─ confirmed → keep the validated scope
        └─ missing → private main-part localization
                           ↓
                     Boundary inference
                     + independent event check for a chapter candidate
                           ↓
                     Validate chapter or exact-passage grant
                           ├─ uncertain → focused clarification
                           ↓
Librarian plans focused needs without seeing passages
                    ↓
Application gathers evidence inside the grant
        ├─ chapter/unit scope → search and rerank each focused query
        │                       + original-text fallback queries
        │                       ↓
        │                 Retain four per planned query in matching books
        │                 + two per fallback query in every granted book
        │                       ↓
        │                 Merge up to 20 canonical records per book
        └─ exact passages → fetch only the granted paragraph IDs
                    ↓
Librarian assesses full records under temporary E1, E2 labels
                    ↓
Application checks selected IDs, coverage, and shared final limit of five
                    ↓
Restore canonical IDs; return selected records and evidence strength
                    ↓
Muse receives a fixed sufficient-result reason; Serendipity keeps the reason
```

Search indexes supply candidates only from the validated chapter or unit scope.
Exact-passage grants fetch fixed canonical records instead. Neither path changes
the boundary or the authoritative source text.

### 2.3 Component ownership

| Component | Responsibility |
|---|---|
| Gutenberg source | Immutable upstream text and download provenance |
| Corpus processor | Verifies the source, extracts exact chapter bodies, renders initial Markdown, and checks integrity |
| Canonical chapter files | Store authoritative chapter bodies and routing front matter in reviewable text files |
| Catalogue builder | Projects canonical front matter into a body-free routing catalogue |
| Book registry | Stores human-reviewed titles, IDs, authors, and classified aliases; deterministic code checks collisions and resolves names |
| Muse | Judges when a request depends on a book, calls `librarian_route`, responds to clarification outcomes, and drafts replies using granted evidence |
| Application boundary | Supplies the original reader message and access scope, resolves identity, validates chapter or exact-passage scope, and enforces reply release |
| Librarian agent | Runs one of four assigned skills: boundary inference, independent event identification, request planning, or evidence assessment |
| Retrieval and reranker services | Localize events privately in main-part numbered chapters, or search inside a granted answer scope; they are not model tools granted to Librarian |
| Sculptor | Proposes chapter cues, retrieval error analyses, and research specifications in offline experiments. Owner-approved changes use temporary corpora or explicit experiment options; production search remains passage-only. Deterministic tooling builds the catalogue |
| Provenance | Runs safety preflight and reviews Muse's draft; cannot grant retrieval access or release a reply itself |
| Serendipity | Proposes connections; has no book-registration or identity-resolution responsibility |

## 3. Offline corpus preparation

### 3.1 Checked-in artifacts

Alice's canonical artifacts are:

```text
data/gutenberg/
└── alice-in-wonderland.txt            # immutable downloaded source

data/corpus/alice-in-wonderland/
└── pg11-v01b38ea4/                    # immutable source revision
    ├── catalog.json                   # derived, metadata only
    └── chapters/
        ├── 01-down-the-rabbit-hole.md # canonical
        ├── 02-the-pool-of-tears.md
        └── ...
```

The source SHA-256 is fixed in the processor and recorded in every chapter's
front matter. A changed source fails validation and requires deliberate review;
the processor does not silently accept a new edition.

### 3.2 Deterministic extraction

The shared corpus lifecycle delegates Gutenberg-specific extraction to the
Alice adapter. That adapter verifies:

- the expected source SHA-256;
- exactly one Gutenberg start marker and end marker;
- the twelve expected contents entries;
- twelve ordered chapter headings and titles; and
- one `THE END` marker after Chapter XII.

It excludes the Gutenberg wrapper, contents page, leading illustration marker,
`THE END`, and licence. It converts CRLF or CR newlines to LF, but otherwise
preserves each chapter body's source layout and Unicode code points exactly,
including hard line wraps, blank lines, indentation, poems, the Mouse's tale,
italics markers, and decorative scene breaks.

The generated Markdown adds only JSON front matter and one Markdown chapter
heading before the extracted body. It does not paraphrase or reflow the source.

### 3.3 Canonical chapter contract

Each chapter begins with validated JSON front matter inside Markdown `---`
delimiters:

```json
{
  "schema_version": 1,
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "chapter_id": "pg11-v01b38ea4-ch01",
  "chapter_number": 1,
  "title": "Down the Rabbit-Hole",
  "routing_description": "Alice follows a watch-carrying White Rabbit...",
  "characters": ["Alice", "White Rabbit"],
  "locations": ["riverbank", "rabbit-hole"],
  "retrieval_cues": ["waistcoat-pocket watch", "DRINK ME bottle"],
  "word_count": 2143,
  "source_path": "data/gutenberg/alice-in-wonderland.txt",
  "source_lines": [58, 272],
  "body_lines": [62, 272],
  "source_sha256": "01b38e...",
  "body_sha256": "e721ad..."
}
```

The fields have three roles:

- `work_id` groups revisions of the same logical work, while `book_version_id`
  and `chapter_id` identify this immutable revision and chapter;
- `routing_description`, `characters`, `locations`, and `retrieval_cues` help
  an agent decide whether to open it; and
- counts, paths, ranges, and hashes support deterministic integrity checks.

Routing metadata is navigation help, not evidence. Quotations and factual book
claims must resolve to the chapter body.

### 3.4 Metadata-only catalogue

`catalog.json` contains both the logical work and immutable revision identity,
plus a projection of each chapter's routing metadata:

```json
{
  "schema_version": 1,
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "title": "Alice's Adventures in Wonderland",
  "author": "Lewis Carroll",
  "source_path": "data/gutenberg/alice-in-wonderland.txt",
  "source_sha256": "01b38e...",
  "chapter_count": 12,
  "chapters": [
    {
      "chapter_id": "pg11-v01b38ea4-ch01",
      "chapter_number": 1,
      "title": "Down the Rabbit-Hole",
      "routing_description": "Alice follows a watch-carrying White Rabbit...",
      "characters": ["Alice", "White Rabbit"],
      "locations": ["riverbank", "rabbit-hole"],
      "retrieval_cues": ["waistcoat-pocket watch", "DRINK ME bottle"],
      "word_count": 2143,
      "path": "chapters/01-down-the-rabbit-hole.md"
    }
  ]
}
```

It contains no chapter body, generated timestamp, chunk size, embedding, or
retrieval score. Rebuilding it reads the canonical front matter and never
rewrites chapter files.

### 3.5 Lifecycle commands

The reusable lifecycle accepts a source-specific adapter. The same commands
apply to each prepared book:

| Book | Adapter | Canonical unit |
|---|---|---|
| Alice's Adventures in Wonderland | `src.linger.corpus.alice` | Chapters, schema 1 |
| Animal Farm | `src.linger.corpus.animal_farm` | Chapters, schema 1 |
| The Adventures of Pinocchio | `src.linger.corpus.pinocchio` | Chapters, schema 1 |
| Narrative of the Life of Frederick Douglass | `src.linger.corpus.douglass` | Sections, schema 2 |
| The Story of My Life | `src.linger.corpus.story_of_my_life` | Sections, schema 2 |

```bash
# One-time creation; refuses to overwrite any existing corpus artifact
uv run python -m src.linger.corpus.book src.linger.corpus.alice init

# Regenerate only the derived catalogue from canonical front matter
uv run python -m src.linger.corpus.book src.linger.corpus.alice build-catalog

# Read-only source, chapter, front-matter, and catalogue verification
uv run python -m src.linger.corpus.book src.linger.corpus.alice check

# Verify a section-based work
uv run python -m src.linger.corpus.book src.linger.corpus.douglass check
```

`--source` and `--output` override the adapter's input and output paths.
Section corpora use `sections/`, `section_id`, and `section_number`; their
catalogues use `section_count` and `sections`. Runtime loading validates each
unit against its registered corpus kind. A chapter registration rejects a
substituted section file; registered section corpora support part-aware chapter
ceilings and exact unit selectors. Preparing a new corpus still requires
deliberate registration before it can supply chat evidence.

Section order is not literary chapter order. Douglass's preface, Phillips
letter, and biography precede Chapter 1, so `sec04` is Chapter 1 and `sec10`
is Chapter 7. Keller's dedication and editor's preface precede Part I, so
`sec003` is Chapter 1 and `sec012` is Chapter 10. The reviewed `unit_locations`
mapping preserves part and chapter identity; letters and supplementary parts
do not inherit chapter numbers from section ordinals.

After initial creation, routing metadata may be edited in the canonical chapter
files and the catalogue rebuilt. The integrity check still requires every
chapter body and deterministic provenance field to match the immutable source.

### 3.6 Verification

Automated checks currently cover:

- immutable-source hashing;
- twelve ordered story chapters with expected titles and line ranges;
- exclusion of contents, illustration, Gutenberg wrapper, and `THE END`;
- exact preservation of source layout and code points;
- deterministic initial rendering and overwrite refusal;
- valid front matter, stable identifiers, checksums, and word counts;
- a metadata-only catalogue in canonical chapter order;
- catalogue rebuilding without changing chapter files;
- rejection of unsupported schema versions;
- catalogue rebuild refusal when canonical structure is invalid;
- detection of missing, unexpected, stale, or tampered artifacts; and
- checked-in corpus freshness.

The shared lifecycle fails on unknown schema versions, validates every
canonical record before replacing the catalogue, and rejects artifacts outside
the complete allowed output tree.

### 3.7 Derived indexes for retrieval evaluation

The required retrieval benchmark derives paragraph windows from canonical
chapter bodies for BM25, semantic, and hybrid search. Every index must:

- be fully regenerable and never become the source of truth;
- retain `work_id`, `book_version_id`, `chapter_id`, and a resolvable source
  location;
- never cross a chapter boundary;
- preserve exact body text for evidence and quotation validation;
- record `book_version_id`, the full source hash, the hash of `catalog.json`,
  and its chunking, embedding, and ranking versions; and
- apply the request boundary before forbidden text reaches a model or reranker.

The benchmark and production hybrid use a 350-word target and 60-word overlap,
contained within one canonical chapter or section. Whole paragraphs can make
windows exceed the target. These are word counts, not tokenizer limits. The
reranker separately fits query/passage pairs to its actual token budget.

### 3.8 Offline input and output contract

The implemented CLI receives explicit source and output paths. At the subsystem
boundary, the equivalent typed input is:

```json
{
  "source_type": "project_gutenberg_text",
  "source_path": "data/gutenberg/alice-in-wonderland.txt",
  "expected_source_sha256": "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
  "output_path": "data/corpus/alice-in-wonderland/pg11-v01b38ea4"
}
```

Successful output describes artifacts that have already passed integrity
checks; it does not contain chapter bodies:

```json
{
  "status": "ready",
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "source_sha256": "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
  "chapter_count": 12,
  "canonical_chapter_directory": "data/corpus/alice-in-wonderland/pg11-v01b38ea4/chapters",
  "catalog_path": "data/corpus/alice-in-wonderland/pg11-v01b38ea4/catalog.json"
}
```

A structural or integrity failure returns no ready corpus:

```json
{
  "status": "review_required",
  "reason_code": "source_structure_changed",
  "message": "Expected 12 ordered chapter headings, found 11."
}
```

## 4. Online retrieval flow

### 4.1 Book identity and contextual routing

Rules: [Specification §6.1](../specification.md#61-spoilers). This section and
§4.2–§4.3 describe how Librarian and the application implement them.

Muse decides whether the requested answer needs a book fact, quotation,
interpretation, an indirect book follow-up, or reading resumption, and then
calls the argument-less
`librarian_route` tool; the application supplies the exact current reader
message from a turn-scoped context variable, so Muse cannot substitute its own
text. An active book selection alone does not justify a tool call. Incidental
words in personal reflection do not require book routing. This intent decision
belongs to Muse's instructions; deterministic routing still validates the
resulting work and access scope. Explicit reading declarations and `route_work` share the deterministic
book registry. Declarations and title-only replies use exact matching; routing
finds reviewed names within the original message. A longer name takes
precedence over names contained inside it, and a canonical title or work ID
beats an alias at the same position. Registered authors can distinguish books
sharing a title. Broad candidate aliases, unresolved shared names, and separate
explicit book mentions require clarification before private boundary inference.
Naming a book never confirms a chapter candidate.

When there is no name signal, `route_work` retains catalogue scoring:
`0.3 + 0.2 × overlap`, capped at `1.0`. Overlap counts distinct whole catalogue
cues; a multi-word phrase contributes one match, nested matches count once,
and generic single-word cues do not count. If no candidate reaches the `0.6`
threshold, routing produces `NoMatch`; multiple qualifying candidates produce a typed
identity clarification, even when their scores differ. A resolved reviewed
name has score `1.0`. These scores are deterministic heuristics, not calibrated
probabilities. When `route_work` itself returns no match, application-side
orchestration falls back to the session's active book selection unless a
strong candidate names a different work; that fallback still hands off to the
same boundary phase, which is free to decline the request.

`work_candidates` uses the same identity resolver for memory selection.
Unresolved names remain weak candidates; catalogue words cannot promote them
to strong support. Without name signals, a distinctive catalogue phrase, two
different non-generic single-word catalogue cues, or broad contextual agreement
can provide strong candidates. Repeated occurrences count once, and generic
single-word cues do not count toward the pair. This selects memories for private
assessment, not reading permission. Librarian must still justify any inferred
boundary from supplied memories and canonical evidence.
The [registration guide](../book-registration.md)
describes the alias policy, collision checks, and agent responsibilities.

A resolved work enters the private boundary phase described below. If a
`NoMatch` leaves a book-dependent request unresolved, Muse asks for its full
title and author; otherwise it can continue personal reflection. For identity
and boundary clarifications from `librarian_route`, application code releases
the validated question after Provenance passes. Muse need not copy it verbatim.
Evidence declarations and non-route tool calls still block release.
A route grants a scope, not source text. Muse calls `librarian_search` with the
returned `work_id` and `book_version_id`. The application supplies the exact
inclusive chapter ceiling, named units, or passage grant from turn context.
A passage route permits only its exact paragraph IDs. A routed
result also names the deterministic `selection_basis` that identified the
work — `resolved_book_identity`, `distinctive_cue`, or `session_selection`.

### 4.2 Input and output contracts

A routed main-part work without confirmed current, carried, or saved permission
enters private boundary inference. Confirmed permission bypasses inference.
A selected non-main part without explicit permission asks for part/chapter or named-unit
clarification. The private boundary phase receives the current Line,
a bounded set of strongly routed account-scoped memories, original earlier
reader statements from the same session, and private main-part candidates.
Current inference searches numbered chapters in `part_id: main`; it does not
localize Keller's letters or supplementary parts, or unnumbered front matter.
Those units require an explicit part or unit scope for answer retrieval.
The book-request skill plans focused reading-progress locators. The application
searches each locator, the original Line, and earlier reader statements before
searching the selected memories. If every reader-context search is empty, the
application returns `insufficient_context` before memory searches or boundary
judgment. Planning failure falls back to the original reader text. Each signal
is split into chunks of at most 2,000 characters. The default hybrid
`retrieve_for_judgement` retains up to 20 records per chunk, even though the
low-level boundary request carries `max_results: 5` for the base retriever.
Application code interleaves results by rank and
deduplicates evidence IDs under one 20-record private candidate limit. This
gives each search stream a chance to contribute before the shared cap. The
searches remain private and grant no reading
permission. Search errors or conflicting text for one ID fail closed.
With earlier reader statements, candidates are narrowed to canonical paragraphs
and the phase can grant exact passages without a completed chapter. See
[Session-supported exact passages](session-passage-design.md). The chapter
inference input excerpt below omits earlier reader statements. It illustrates
localization input, not sufficient proof for a chapter grant:

```json
{
  "current_line": "Why does Alice struggle to explain who she is?",
  "relevant_memories": [
    {
      "memory_id": "mem_01K2...",
      "text": "The Caterpillar's questions made me think about how uncertain I am about my identity.",
      "evidence_ids": ["pg11-v01b38ea4-ch05-ln0974-0981"]
    }
  ],
  "full_work_candidates": [
    {
      "evidence_id": "pg11-v01b38ea4-ch05-ln0974-0981",
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "chapter_number": 5,
      "text": "Private canonical passage used only for localization"
    }
  ]
}
```

In the same boundary invocation, Librarian returns `memory_assessments` before
its chapter decision: one assessment for each supplied memory, with its exact
ID, status, canonical evidence IDs and a short reason. It can ground a memory
from the supplied passage text even when the stored memory has no evidence IDs.
The model must account for earlier knowledge separately from locating the
current reading report. A grounded memory cannot be omitted from a candidate's
support; a conflicting assessment cannot authorize a candidate.

`BoundaryMemoryValidation` provides structured coverage and consistency errors
within the existing single retry. Application code repeats those checks before
granting access. It never changes a line-only answer into a memory-supported
one itself. An ambiguous current event can still produce `uncertain` despite
grounded earlier knowledge. These assessments do not change session-supported
exact-passage grants.

A chapter candidate also contains an `event_resolution` inventory covering every
supplied passage exactly once. It identifies one selected occurrence and rules
out alternatives using exact reader spans. Every supporting record carries a
literal `source_excerpt` from its own canonical text. Unresolved alternatives
require uncertainty, even when the memories establish earlier knowledge.

Before accepting an otherwise valid chapter candidate, the application runs
`identify_reader_event` with the original reader wording and private canonical
candidates. This run receives no memories, proposed chapter, or first decision.
Its selected stopping occurrence must agree with the candidate's chapter and
overlap a selected canonical source range in that chapter, with matching work,
revision, unit ID, and source hash. Unresolved identification, disagreement,
invalid output, or execution failure grants nothing. This check does not apply
to the separate session-supported passage path.

Private Librarian runs retain the candidate text, and only boundary inference
receives the memories. The application's accepted handoff contains no passage
text or assessment rationales:

```json
{
  "kind": "candidate",
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "max_chapter_inclusive": 5,
  "confidence": 0.93,
  "authorization_basis": "memory_supported",
  "supporting_memory_ids": ["mem_01K2..."],
  "supporting_locations": [
    {
      "evidence_id": "pg11-v01b38ea4-ch05-ln0974-0981",
      "chapter_number": 5,
      "location": "Chapter 5, source lines 974-981"
    }
  ]
}
```

Application code validates the selected registered work, supporting memory IDs,
canonical evidence IDs, derived chapter, and authorization basis. A Line-only
question can locate an event but cannot authorize a ceiling; it requires one
exact clarification even at high model confidence. A validated
memory-supported candidate receives a request-scoped retrieval grant. The
application binds that scope and the original reader question for the separate
bounded evidence phase:

```json
{
  "request_id": "libreq_01K2...",
  "query": "Why does Alice struggle to explain who she is?",
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "access_scope": {
    "allowed_book_version_ids": ["pg11-v01b38ea4"]
  },
  "options": {
    "retrieval_score_threshold": 0.5,
    "max_final_evidence": 5
  }
}
```

Application code creates `access_scope` and obtains reading permission from
the active turn. Neither field comes from model output. Thresholds may be
overridden by evaluated configuration, but no agent may lower them or enlarge scope.

### 4.3 Boundary enforcement and clarification

Boundary inference and answer-evidence retrieval are separate calls. Without
earlier reader statements, the application selects the chapter-only boundary
output contract. With those statements, the same boundary skill can also
propose exact passages; that branch uses its own statement and paragraph checks.

The chapter path is:

1. The inference search may inspect all numbered main-part chapters, but its
   passages remain private and never enter the turn evidence ledger.
2. Librarian assesses every supplied memory against canonical candidates, then
   declares a consistent `memory_supported` or `line_only` basis and selects
   only input memory and evidence IDs.
3. Application code derives the ceiling from those trusted records and rejects
   invented memory or evidence IDs, a mismatched work or revision, an invalid
   basis, and inconsistent chapters.
4. Line-only curiosity, confidence below `0.75`, or unresolved ambiguity yields a clarification; the
   release validator rejects a book answer or tool call in its place.
5. Independent event identification must confirm the proposed stopping occurrence.
6. A validated candidate enables a new search whose scope is clamped to the
   inferred ceiling. The inferred boundary is absent from durable account progress.

At chapter granularity:

- Chapter 5 `completed` permits Chapters 1 through 5.
- Chapter 5 `started` permits Chapters 1 through 4.
- A grounding request without a validated grant returns clarification before
  answer-evidence retrieval. A prior routing call may already have searched
  privately to try to establish that grant.

During the second phase, post-boundary catalogue entries and chapter bodies
must not reach the evidence judge, Muse, a bounded index, a reranker, or any
downstream answer context. The private first-phase Librarian is the sole
exception and has localization authority, not disclosure authority. Inferred
permission is resolved within the request. Explicit reader progress follows the
session and account rules below.

Clarification is a distinct response type, not a weak or empty retrieval
result:

```json
{
  "kind": "clarification",
  "request_id": "libreq_01K2...",
  "clarification_id": "clar_01K2...",
  "reason_code": "reading_boundary_unconfirmed",
  "question": "What book and chapter have you confirmed reading so far?",
  "expected_answer": {
    "type": "free_text"
  }
}
```

A clarification contains no evidence, retrieval score, or evidence-strength
label because no answer evidence is released. Private localization may already
have searched before the application asks for clarification. Muse presents the focused question and sends
the answer through the same trusted boundary validator.

General partial-current-chapter ceilings remain unsupported. Exact canonical
paragraph IDs support the narrower session-passage permission described in
[Session-supported exact passages](session-passage-design.md), without implying
completion of the chapter or permission for neighboring text.

#### Explicit session and account progress

The session carries a reader-confirmed chapter through ordinary follow-ups
about the same work and part. A lower declaration applies immediately, even
when the turn fails or declines. A higher declaration commits only after a
released Muse reply or application clarification. An unclear correction
retracts the carried ceiling and supersedes earlier reader statements.
Application code excludes prior evidence outside the current ceiling. Changing
book or part, deleting the session, or restarting the backend clears session
progress.

The interactive application's `ReadingProgressStore` persists the part and
completed chapter per account and work in
`LINGER_STATE_DIR/reading_progress.sqlite3`. A lower declaration reduces an
existing same-part saved ceiling before model execution. A withdrawal removes
the saved permission immediately. Both changes survive a declined, failed, or
cancelled turn. A higher declaration requires a released Muse reply or
application clarification. Saved progress survives conversation
deletion and backend restarts. Loading validates the current registered
revision, access list, part, and chapter count. The store contains no inferred
boundaries, named units, or exact-passage grants.

Saved progress never selects a work. Current-turn context preparation applies
it only to an identified book, behind that session's progress or retraction,
and withholds it when an unparsed correction speaks to progress. Book routing
can bind saved progress after identifying a work and matching its part.
A newly accepted retraction also removes the saved account record. An unrelated
later turn does not repeat an old session's withdrawal or write its carried
chapter back to the account.

`apps/backend/progress_store.py` keeps a separate revision for each account and
book. Every accepted declaration or withdrawal advances that revision in a
short SQLite transaction. Withdrawal retains the revision after deleting the
permission. This prevents an older reply from recreating withdrawn progress,
even if another conversation has since saved the same chapter again. Existing
databases retain their permission rows when the revision table is added.

`apps/backend/chat_turn.py` saves a released declaration only if its revision
is still current. It checks after memory curation, beside the session-progress
commit, so a correction during curation also wins. Saved-progress snapshots
carry their revision to prevent stale permission from entering a conversation.
If a newer statement invalidates the pending update, the application narrows
the session against current permission and supersedes its stale reader
statements. The application holds no database transaction while awaiting a
model reply.

For example, conversation A declares chapter 7 while its reply is pending.
Conversation B then corrects progress to chapter 2. When A finishes, its older
revision cannot replace chapter 2 in either saved progress or its session.

For `find_connection`, the application combines saved progress with any current
confirmed permission. When that covers at least two books, it supplies each
book at its own ceiling without a primary book. The current permission replaces that book's
saved entry. Synthetic replay uses trusted supplied scopes and omits live
account progress. `tests/test_reading_progress.py` covers session corrections;
`tests/test_progress_store.py` covers durable storage, account isolation, saved
routing, and comparison scopes. `tests/test_progress_persistence.py` covers
failed-turn restrictions and sequential conversations.
`tests/test_progress_ordering.py` covers overlapping replies, withdrawals,
deletion and recreation, and corrections during curation.

#### Declarations, retractions, and clarification follow-ups

Rules: [Specification §6.1](../specification.md#61-spoilers).

**What declares progress.** Only the reader's explicit completion statement or
clarification answer declares a chapter. Questions, conditions, and explicit
uncertainty about completion do not. Quoted, blockquoted, or fenced text
declares nothing.

**What retracts progress.** Any other turn that may speak to progress retracts
the carried ceiling and fails closed. That covers:

- a statement, or a question with a correcting or limiting cue such as "sorry",
  "only", "not", "beyond", "stay within", or "stop at", that names an earlier
  chapter's title or location;
- a number within the book's chapters alongside a chapter word or such a cue,
  or in a reply of four words or fewer;
- progress language with no number, such as "I haven't met…", "don't spoil…",
  or "a different book"; and
- a parser clarification.

Quotes do not shield a retraction. Lowering or retracting hides earlier reader
statements from boundary inference and withholds earlier cited passages the
ceiling no longer permits. Per-work corrections remain until a session reset or
restart, so returning to a book cannot restore a retracted permission. A
restart also hides restored reader statements from boundary inference.

**Precedence.** A declaration in the current message outranks the session's
declaration or retraction, which outranks saved progress. Direct restoration of
saved progress records the `saved_progress` authorization basis. A saved chapter
that no longer fits the registered, permitted work is ignored. A routed inferred
ceiling never widens or replaces a boundary the reader confirmed this turn.

**Unreadable memory storage.** The application binds an empty memory set and
boundary inference proceeds without memories. A chapter ceiling still requires
memory support; earlier reader statements may still support exact passages.

**Chapter numbering.** Chapter numbering restarts where the source does, while
canonical section IDs keep source order. Chapter 1 in Part I and Chapter 1 in
Part III of *The Story of My Life* are distinct locations. `chapter_id` stores
the canonical unit ID; `chapter_number` stores the literary chapter number, or
`null` for named sections.

**Cached indexes.** Cache scope identity is the work, revision, part, and
chapter ceiling or exact unit IDs. Excessive ceilings are clamped to the part's
registered maximum before lookup. Exact unit membership is validated even when
an index is cached.

**Below-cutoff grounding.** For direct grounding, if every fused candidate falls
below the final reranker cutoff, the application may keep the highest-ranked
eligible candidate for evidence-strength assessment. Only an accepted
assessment admits it to the release index. Ordinary retrieval, connection
search, and boundary inference keep their cutoffs.

**Cross-book comparison.** When turn triage classifies a message as a connection
request and the reader has confirmed two or more books, the turn runs as the
unfocused `connection_book_scopes` comparison. Each book is granted at its own
ceiling and none is primary. A book confirmed this turn replaces its saved
value. An undeclared book is never searched.

**Clarification release.** An unresolved routing or boundary clarification
returns a typed `ClarificationRequest` from `librarian_route`. After Provenance
passes the candidate, the application releases the validated question as
`application_clarification`, replacing Muse's wording. Evidence declarations and
non-route tool calls still fail validation, and an emotional boundary takes
priority. Clarifications suppress capture with
`clarification_capture_suppressed`. The released question and original reader
message stay in session history with the pending clarification state.

**Clarification answers.** A later reply that is only a chapter reference, such
as "2", "two", "second", or "chapter two", counts as completed progress only
when a clarification is pending and the chapter exists in the selected part. It
resolves as `reader_confirmed` before Muse runs, and Muse re-issues the original
book question through `librarian_search` under that ceiling. Hedged or
question-shaped replies, unrelated text, and out-of-range answers keep the
question pending. Unresolved identity or a book switch clears it. Direct search
checks identity from the original message or validated session selection before
recording a pending question.

Only a memory-supported clarification that asks about a specific candidate
chapter may retain that chapter for a follow-up affirmation. A generic progress
question clears any earlier candidate. Naming the book or saying the chapter is
unfinished does not confirm progress. When the same progress question stays
unanswered for a single-part, chapter-based work, routing asks a closed question
for a chapter number within range. Mixed section-based works keep the ordinary
clarification.

A routed work derives Provenance's review context after Muse runs. A
`RoutedWork` result grants that reading context only when no boundary was
already resolved.

### 4.4 Retrieval, fusion, and deduplication

The benchmark used direct bounded chapter selection as its control. The
selected hybrid retrieval path serves both Muse grounding and Serendipity book
search through the same judged retrieval operation:

```text
Application-supplied reader cue, earlier reader statements, and validated scope
        ↓
Librarian plans the book request without seeing candidate passages
        ↓
Search each planned book need and retain the original reader text as fallback queries
        ↓
Filter catalogue and indexes to eligible chapters
        ↓
Keyword search (up to 10) + semantic search (up to 10, no private score cutoff)
        ↓
Preserve independent keyword and semantic candidates by evidence identity
        ↓
At most 20 private candidates per query
        ↓
Reranker scores overlapping token windows and retains each passage's best score
        ↓
Interleave keyword, fused, semantic, and reranker results; retain four per planned query
        ↓
Keep each part in clearly matching books, plus two fallback candidates per query per book
        ↓
Remove fully contained windows; merge into at most 20 candidates per book
        ↓
Resolve final passages to exact canonical chapter lines
        ↓
Librarian assesses the plan and original reader request against the permitted evidence set
```

Muse `librarian_search` and Serendipity `search_librarian` accept no
model-written book query. Application code supplies the original reader cue and
earlier reader statements to `plan_book_request` before retrieval. Each planned
book need becomes a separate query from its exact reader spans. The plan
identifies each named event in a requested sequence separately. The original
current message and earlier reader statements remain fallback queries, including
when planning fails or omits a need. Before each query searches a book,
application code removes its registered author-name words unless they also
appear in the title or aliases. Reader-span validation and evidence text retain
the original wording. Queries are split into chunks of at most
2,000 characters, with at most 16 distinct queries. Exceeding that budget fails
without widening scope or silently dropping the remaining reader input.

Both callers use `retrieve_for_judgement`. The hybrid retriever returns up to
20 private candidates per query, interleaving keyword, fused, semantic, and
reranker results. These records have no public score cutoff. Reranking uses
overlapping windows that fit the encoder's token budget and assigns each
canonical passage its maximum window score. Evidence text and source ranges
remain unchanged. Scope filtering happens before retrieval and judgment.

`gather_book_candidates` searches each planned query in every allowed book.
It retains four candidates in the strongest-matching book when that book's
best score is at least 0.05 and at least ten times the next book's best score.
Otherwise, it retains four per book. Four covers the opening round of all four
retrieval methods, including a reranker leader that appears fourth in the
interleaved list. The list is not sorted by reranker score.

The original Line and each prior reader statement independently retain two
candidates per query per book. This fallback also applies to books excluded
by part routing. Identical searches share cached results within the invocation,
keyed by the complete book scope and effective query. Query reuse does not
remove the fallback allowance. Without planned queries, each fallback query
retains up to 20 candidates per book.

The application interleaves the retained streams, removes fully contained
windows, and caps the result at 20 records per book. This is a bounded recall
policy: a large request can still exceed the merged budget. Experiment 4 can
override the per-part allowance with `part_candidates=20`; production uses four.
Experiment 4 result identities include retrieval source hashes and the candidate
allowance, so results from older retention rules are stale.

The caller's release limit is separate from this private budget and is supplied
as `max_evidence_records`. Muse clamps `max_final_evidence` to 1–5. Serendipity
clamps `max_results_per_source` to 1–5 for the selected book search. It can
select an allowed `work_ids` subset when multiple books are available. A
title-free reading connection with `search_all_granted_books` searches every
granted work regardless of the model's subset. The final record budget is
shared across that search, not multiplied by the number of books. The judge
assesses the original request alongside
the plan, including omitted needs. An oversized or invalid selection fails
closed instead of silently truncating the evidence behind its verdict.

For example, a comparison with three granted books can supply up to sixty
private records to one assessment. The caller's five-record limit still applies
to the final selection across those books. If those five records cannot support
every requested part, the assessor must return `weak` with the missing support,
or `none` when no useful support exists. The per-book cap does not promise
complete recall for every multipart request.

Both callers receive `sufficient`, `weak`, or `none`, with a reason and
limitations. Only judge-selected canonical records return to the caller. A
rejection returns no evidence. Retrieval or judge failure returns a typed
failure with no evidence. Serendipity receives the strength, reason, and
limitations in the book search result's `judgement` field. It separately
evaluates whether the selected evidence supports a broader connection. Weak
source evidence may support a limited comparison, but Serendipity declines when
the evidence cannot support the proposed relationship. Provenance still
reviews Muse's final response. Ordinary public `retrieve` keeps its cutoff and
15-candidate fused shortlist. Private boundary inference uses the broader
judgment pool, then separately validates reading permission. Neither private
operation widens disclosure scope or lowers the public retrieval cutoff.

This handles a verified false negative in Douglass: the literacy passage in
Chapter 6 ranks first for the Hugh Auld question but scores about 0.352 against
the 0.5 cutoff. Finishing Chapter 7 already permits that passage; changing the
corpus numbering or widening the spoiler boundary would not repair the miss.

The restriction is applied before search. Duplicate evidence IDs keep one
canonical record. During private candidate gathering, a later window is removed
only if an earlier window contains its entire source range in the same work,
revision, part, chapter, and source hash. Partial overlaps remain because their
unique lines may contain the answer. Ordinary public retrieval still suppresses
strongly overlapping windows in its fused shortlist. Candidate selection never
paraphrases or stitches source text.

`HybridLibrarian(read_chapter_cues=True)` appends each chapter's reviewed
description, characters, and retrieval cues to the text used by BM25,
embeddings, and reranking. Cues follow the passage so embedding truncation
discards cue text first. They never enter canonical evidence excerpts or alter
evidence IDs. The index identity includes cue metadata when this option is
enabled. Production defaults to passage-only search. The
[offline evaluation commands](../../evals/librarian/README.md#chapter-cue-and-retrieval-research-experiments)
use temporary corpus copies for approved cue revisions.

Sculptor's offline `chapter-cues`, `retrieval-error-analysis`, and
`retrieval-research` skills propose changes for these experiments. Approved
research specifications bind experiment identities; they do not configure the
interactive application. The `round1` condition uses approved Stage 2 cues and
twenty windows per planned part, while retaining the twenty-record cap per book.
See [Sculptor's assigned skills](../../src/linger/agents/sculptor/skills.py),
the [experiment runner](../../evals/librarian/chapter_cue_recall.py), and the
[Experiment 4 report](../evaluation/retrieval-research-experiment-4-2026-10-01.md).

### 4.5 Reranking versus evidence strength

These are separate decisions:

| Stage | Owner | Question answered | Output |
|---|---|---|---|
| Public retrieval threshold | Application retrieval service | Does this candidate clear the public cutoff? | Candidate kept or removed; private judged retrieval bypasses this cutoff |
| Reranking | Application reranker service | Which individual candidate best matches this query? | Ordered candidate list |
| Evidence-strength decision | Librarian agent | Can the eligible evidence set actually answer Muse's request? | `sufficient`, `weak`, or `none` |

A high retrieval or reranker score does not prove that the passage answers the
question. It may match the same words while missing the requested relationship
or explanation. Conversely, `weak` evidence still includes its full evidence
details so Muse can explain the limitation instead of losing context.

The reranker measures query and passage tokens against its configured pair
limit. Oversized pairs are scored through overlapping token windows, retaining
the highest score for each canonical record. Evidence IDs, text and source
locations remain unchanged. This prevents silent truncation of the decisive
text; it does not turn a local relevance score into a probability of support.

Librarian identifies the requested book parts before private retrieval through
`plan_book_request` and its book-request skill. Muse and Serendipity supply the original reader message and available
earlier reader statements, so a progress clarification can resume the original
question. Standalone calls use their caller's question. This invocation sees no
candidate passages or expanded search query. Each part contains exact
`context_spans`, `purpose`, and exact `reader_spans`, with no free-form rewritten
question. Context retains the book, scene, or speaker needed to resolve a
question's pronouns, including a locator from the preceding reading report.
Context can be empty for a self-contained question or title-free thematic
discovery and creates no extra answer requirements. Retrieval joins context
before the requested wording. For named-book questions the skill selects short
book locators, excluding unrelated personal asides. For an explicit request to
find an unnamed book connection, it can retain the reader's action, relationship,
or tension as the discovery cue. `search_target: reading_progress` instead
selects progress locators. Application code validates the nonempty reader spans,
any supplied context spans, and the purpose against the original input.

`BookRequestSpanValidation` checks the plan before the Agent run completes.
Invalid spans receive their field locations and repair guidance within the
existing single output retry. A unique case-only match can supply an exact
reader-span suggestion; it does not make the original span valid. The
capability leaves other Librarian outputs unchanged. `plan_book_request` uses
the same `book_request_span_errors` helper to reject any remaining invalid
span before retrieval.

`assess_book_evidence` reuses the plan that drove retrieval with the permitted
canonical records. A `reference` grounds the named book moment for reflection or a
comparison. An `answer` addresses an explicit book question, claim check, or
quotation request, even when the answer is used in reflection. Its instructions
require the smallest set supporting that purpose. Another record is warranted
only when removing it would leave a requested part unsupported. A quotation can require several records; a personal
reflection does not by itself require more book passages. The assessment may
recover omitted original needs in `additional_parts`, anchored to exact reader
spans. It must not invent needs to justify available evidence. Recovering a need
at this stage does not trigger another retrieval pass.

`BookEvidenceAssessment.support` maps every selected record to an existing
`part_index` across the plan and recovered parts, and explains its
`necessary_support`. Deterministic checks require
unique mappings, valid selected IDs, and coverage of every part for a
`sufficient` verdict. Selection must also fit `max_evidence_records`. Application
validation supplies span, support, coverage, and selection errors to the
Agent's single repair retry. Unknown IDs receive up to three similar supplied
IDs as repair suggestions, without silently changing the output. Application
code returns the existing `EvidenceStrengthDecision` fields to either caller.
The mapping's meaning remains a model judgment; structural validation does not
prove that a passage answers the question. No request plan changes reading
scope, source identities, or the caller's evidence authority. Exact passage
grants use the same planner and assessor over their fixed records. They never
trigger broader retrieval.

The assessor sees short labels such as `E1` and `E2` in place of long evidence
IDs. Every other field, including the complete passage, source hash, and line
range, stays intact. After validating the assessment, application code maps
selected labels back to canonical IDs. Labels mentioned in reasons or
limitations become readable source locations. These labels are private to one
assessment and never become persistent evidence identities.

Planning and assessment each permit one output repair and at most two model
requests. Unknown tool calls cannot extend those request budgets. The
application repeats domain validation after the Agent returns, so injected
agents and captured replay results must satisfy the same checks.

Muse does not receive Librarian's free-text reason for a `sufficient` result.
The `librarian_search` adapter replaces `strength_reason` with one fixed
application sentence: "The selected records were judged sufficient for the
reader's request." Every other field stays as judged. `weak` and `none` results
keep the model's reason, which Muse states only for `weak` evidence.
Provenance reviews the tool result Muse saw; Serendipity and Librarian's own
recorded assessment keep the full reason.

Librarian does not supply a separate list of stated answers or run a fifth
answer-extraction skill. The October 12 answer-list experiment was reverted.
Muse drafts from the returned source records, and Provenance reviews that draft.

The reranker does not order candidates by `sufficient`, `weak`, and `none`.
Those labels describe the combined final result, after reranking and canonical
resolution.

### 4.6 Evidence identity

Final book evidence uses a revision-aware, line-resolvable identifier:

```text
pg11-v01b38ea4-ch05-ln0974-0981
│    │          │    └─ inclusive lines in the immutable source
│    │          └────── chapter number
│    └───────────────── prefix of the full source SHA-256
└────────────────────── stable work ID
```

The work ID and source-hash prefix together identify the immutable book revision.
The evidence record also carries the full source hash. A shortened-hash
collision is a hard failure. Candidate-window IDs may exist inside a derived
index, but Muse and Provenance receive the final canonical line-based evidence
ID.

### 4.7 Result contract

When retrieval runs, Librarian returns `kind: result`. This is distinct from a
clarification. A sufficient result as grounding judges it looks like this;
Muse's `librarian_search` shows the fixed sentence from section 4.5 in place of
this `strength_reason`:

```json
{
  "kind": "result",
  "request_id": "libreq_01K2...",
  "outcome": "evidence_found",
  "evidence_strength": "sufficient",
  "strength_reason": "The eligible passage directly describes Alice's difficulty explaining her identity after repeated size changes.",
  "searched_scope": {
    "work_id": "pg11",
    "book_version_id": "pg11-v01b38ea4",
    "max_chapter_inclusive": 5
  },
  "evidence": [
    {
      "evidence_id": "pg11-v01b38ea4-ch05-ln0974-0981",
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "chapter_id": "pg11-v01b38ea4-ch05",
      "chapter_number": 5,
      "location": "Chapter 5 — Advice from a Caterpillar, source lines 974-981",
      "source_sha256": "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
      "source_lines": [974, 981],
      "text": "“I can’t explain _myself_, I’m afraid, sir,” said Alice, “because I’m\nnot myself, you see.”\n\n“I don’t see,” said the Caterpillar.\n\n“I’m afraid I can’t put it more clearly,” Alice replied very politely,\n“for I can’t understand it myself to begin with; and being so many\ndifferent sizes in a day is very confusing.”"
    }
  ],
  "limitations": []
}
```

`EvidenceRecord` carries canonical identity, location, hash, lines, and text.
It does not include `chapter_title` or retrieval scores in the public contract.
Internal candidates retain ranking diagnostics. For weak evidence, the same
required evidence fields are present. This abbreviated example omits identity
and hash fields for readability and is not a complete serialized result:

```json
{
  "kind": "result",
  "request_id": "libreq_01K2...",
  "outcome": "evidence_found",
  "evidence_strength": "weak",
  "strength_reason": "The passage shows confusion about identity but does not establish the broader motive asked about.",
  "searched_scope": {
    "work_id": "pg11",
    "book_version_id": "pg11-v01b38ea4",
    "max_chapter_inclusive": 5
  },
  "evidence": [
    {
      "evidence_id": "pg11-v01b38ea4-ch05-ln0974-0975",
      "chapter_id": "pg11-v01b38ea4-ch05",
      "source_lines": [974, 975],
      "text": "“I can’t explain _myself_, I’m afraid, sir,” said Alice, “because I’m\nnot myself, you see.”"
    }
  ],
  "limitations": ["No eligible passage directly states the requested motive."]
}
```

No evidence is still a completed result, not a clarification:

```json
{
  "kind": "result",
  "request_id": "libreq_01K2...",
  "outcome": "no_evidence",
  "evidence_strength": "none",
  "strength_reason": "No useful support was found inside Chapters 1–5.",
  "searched_scope": {
    "work_id": "pg11",
    "book_version_id": "pg11-v01b38ea4",
    "max_chapter_inclusive": 5
  },
  "evidence": [],
  "limitations": []
}
```

The response is a discriminated union:

```text
LibrarianResponse
├── ClarificationRequest   kind = clarification; no answer evidence is released
├── RetrievalResult       kind = result; completed with sufficient/weak/none
└── RetrievalFailure      kind = failure; system could not complete safely
```

A retrieval failure is reserved for unavailable or corrupt dependencies, an
unresolvable evidence ID, or another safe-completion failure. It is not used for
ordinary `no_evidence`.

### 4.8 Failure behaviour

Retrieval fails closed when the boundary or evidence location cannot be
validated. The current grounding path returns `retrieval_unavailable` for
retrieval failures and `evidence_judgement_unavailable` for assessment failures.
It does not automatically fall back to direct chapter reads or retry the whole
retrieval. Serendipity returns an unavailable internal search result on failure.
Planning alone has an original-text fallback. The grounding failure includes a
stable error code and retryability flag, but no unvalidated excerpt; retryability
does not schedule a retry.

### 4.9 Online verification

These source and test pairs cover the current contracts. They are regression
coverage, not a new provider-quality benchmark.

| Behavior | Implementation | Focused checks |
|---|---|---|
| Exact reader spans, recovered needs, coverage, short labels, and repair | [Request models](../../src/linger/agents/librarian/models.py), [assessment dispatch](../../src/linger/orchestration/evidence_strength.py) | [Request plans](../../tests/test_librarian_request_plan.py), [evidence strength](../../tests/test_evidence_strength.py) |
| Separate planned queries, original-text fallback, and per-book budgets | [Candidate gathering](../../src/linger/orchestration/book_evidence.py) | [Request recall](../../tests/test_book_request_recall.py), [part-scoped retrieval](../../tests/test_part_scoped_retrieval.py), [multi-book selection](../../tests/test_serendipity_book_selection.py) |
| Four retrieval streams, partial-overlap retention, and independent fallback | [Candidate gathering](../../src/linger/orchestration/book_evidence.py), [hybrid retrieval](../../apps/backend/hybrid_librarian.py) | [Candidate retention](../../tests/test_book_candidate_retention.py) |
| Full text reaches token-window reranking, including intermediate and tail windows | [Token-window reranker](../../apps/backend/rerank_windows.py) | [Reranker windows](../../tests/test_rerank_windows.py) |
| Each nested Librarian call stops at its own request budget | [Assessment dispatch](../../src/linger/orchestration/evidence_strength.py) | [Usage limits](../../tests/test_usage_limits.py) |
| Canonical evidence, chapter and part boundaries, and exact-passage grants | [Hybrid retrieval](../../apps/backend/hybrid_librarian.py), [grounding](../../src/linger/orchestration/grounding.py) | [Hybrid retrieval](../../tests/test_hybrid_librarian.py), [mixed-book retrieval](../../tests/test_mixed_book_retrieval.py), [passage grounding](../../tests/test_passage_grounding.py) |
| Explicit progress persists per account and work without granting inferred progress | [Progress store](../../apps/backend/progress_store.py), [saved-progress application](../../apps/backend/chat_turn.py) | [Reading progress](../../tests/test_reading_progress.py), [durable progress](../../tests/test_progress_store.py) |
| Only Muse's sufficient-result reason changes; evidence and other outcomes survive | [Muse tools](../../src/linger/agents/muse/tools.py) | [Search reason](../../tests/test_muse_search_reason.py), [route and release](../../tests/test_librarian_route_e2e.py) |
| Offline chapter cues affect search without entering canonical excerpts | [Hybrid retrieval](../../apps/backend/hybrid_librarian.py), [experiment runner](../../evals/librarian/chapter_cue_recall.py) | [Hybrid retrieval](../../tests/test_hybrid_librarian.py), [chapter-cue replay](../../tests/test_chapter_cue_recall.py) |

## 5. Downstream integration

Muse switches on `kind` before it drafts anything:

| Librarian response | Muse action |
|---|---|
| `clarification` | Ask the supplied focused question; do not draft a book answer and do not treat it as weak evidence |
| `result` + `sufficient` | Draft an evidence-grounded candidate and cite only returned evidence IDs |
| `result` + `weak` | Include the returned evidence context, clearly state the limitation, and avoid unsupported conclusions |
| `result` + `none` | Say the eligible material did not provide support; never imply later chapters were searched |
| `failure` | No evidence is supplied; handle unavailable retrieval safely. The retryable flag does not automatically rerun the search |

A Librarian result is evidence for Muse, not permission to display a response:

```text
Librarian evidence bundle
      ↓
Muse drafts typed candidate response
      ↓
Provenance reviews complete response, claim coverage, source contributions,
and quotation attribution
      ├─ revise → one Muse revision → another Provenance review
      ↓
Application validates exact quotations, source locations,
account scope, and request-scoped spoiler boundary
      ↓
Release or application-authored safe decline
```

Muse should distinguish direct evidence from interpretation and state when the
eligible material is weak or silent. Provenance independently determines
whether the resulting response is supported and spoiler-safe.

## 6. Current configuration

The canonical corpus has no retrieval tuning fields. These are application
retrieval defaults, not measurements of normal performance:

```yaml
derived_windows:
  target_words: 350
  overlap_words: 60
  cross_unit: false

public_retrieve:
  keyword_candidates: 10
  semantic_candidates: 10
  semantic_score_threshold: 0.5
  max_fused_candidates: 15
  reranker_score_threshold: 0.5

judged_retrieval:
  keyword_candidates: 10
  semantic_candidates: 10
  public_score_cutoffs_applied: false
  max_private_candidates_per_query: 20
  candidates_per_planned_part: 4
  candidates_per_context_query: 2
  max_merged_candidates_per_book: 20
  max_query_characters: 2000
  max_distinct_queries: 16

production_final_selection:
  default_records: 5
  maximum_records: 5

book_request_and_assessment:
  max_planned_parts: 8
  output_repairs_per_run: 1
  model_requests_per_run: 2
  assessment_evidence_labels: E1, E2, ...

offline_options:
  read_chapter_cues_default: false
  round1_candidates_per_planned_part: 20
  round1_max_merged_candidates_per_book: 20

private_boundary:
  part_id: main
  numbered_chapters_only: true
  max_memories: 8
  max_merged_candidates: 20
  confidence_threshold: 0.75
```

The semantic search bypass uses cosine floor `-1.0`; the private path applies
no reranker cutoff. Public `retrieve` retains the configured cutoffs. Final
production selection is judged and capped by each tool adapter. The shared
`RetrievalOptions` schema permits up to ten records, but Muse's production
adapter clamps its argument to five. Reranker window lengths come from the
encoder tokenizer's actual pair budget, not these paragraph-window word counts.

## 7. Implementation history and saved measurements

The milestones and measurements in this section are historical. They do not
establish that all current native scenarios pass or that new runtime paths have
been benchmarked. Current code is the authority for behavior; Beads tracks
remaining work.

The [design history](../reports/librarian-experiments-2026-09-24/design-history.md)
and its [interactive view](../reports/librarian-experiments-2026-09-24/design-history.html)
cover later experiments and the changes present after the October 14 rebase.

### 7.1 Initial product milestones

| Order | Slice | Status | Deliverable | Beads |
|---:|---|---|---|---|
| 1 | Offline corpus and hardening | Complete | Verified immutable source, revision-aware canonical chapters, derived catalogue, reusable lifecycle, and deterministic checks | `linger-tz2` |
| 2 | Contracts and spoiler boundary | Complete | Typed request/response models and trusted completed/started/ambiguous chapter enforcement before corpus access | `linger-ibq.1` |
| 3A | Bounded direct evidence retrieval | Complete | Canonical reads, thresholds, no-match behavior, exact line-range evidence IDs, pre-read spoiler filtering, and independent strength judgement | `linger-ibq.2` |
| 3B | Muse response integration | Complete | Separate handling for clarification, sufficient, weak, none, and failure | `linger-ibq.3` |
| 4 | Retrieval benchmark and selection | Complete | Five versioned configurations compared; reranked hybrid selected and implemented | `linger-ibq.5` |
| 5 | End-to-end validation | Complete | Selected strategy, spoiler suppression, evidence resolution, failures, safe degradation, live strength judgement, and Muse/Provenance release measured against the full versioned set | `linger-ibq.4` |

These initial milestone statuses describe the original implementation scope.
They are not a claim that every later multi-book, ambiguity, and source-mapping
evaluation passes.

### 7.2 Separate memory implementation

> **Deferred:** This design is outside the current POC. The interactive product
> exposes no memory-management interface; see the canonical
> [system specification](../specification.md).

Linger adopts the public Anthropic Managed Agents memory pattern while keeping
memory outside Librarian. The complete contract is in
[`memory-format.md`](memory-format.md); its core records are:

| Record | Purpose | Important fields |
|---|---|---|
| `memory_store` | Account-scoped boundary for one owner and lifecycle | `store_id`, trusted `account_key`, `status` |
| `memory` | Stable live record containing the current user-approved Markdown | stable `memory_id`, `path`, `current_version_id`, `content_sha256` |
| `memory_version` | Immutable snapshot appended for every create, correction, or delete | `version_id`, `memory_id`, `operation`, `previous_version_id` |
| `memory_derivation` | Replaceable generated summary, duplicate link, or relationship | `derivation_id`, `source_version_ids`, generator metadata |

The Anthropic-inspired behaviour is concrete: create never overwrites an
existing memory; update may change content or path only with a current-content
hash precondition; every successful mutation appends an immutable version; and
agents that only need context receive a read-only view.

Linger adds two product rules. Muse and Sculptor submit typed proposals instead
of writing memory directly, so the Memory & Policy Service owns account scope,
consent, IDs, paths, idempotency, and concurrency. An authorized deletion
purges the live body, historical version bodies, derivations, and derived-index
entries rather than retaining deleted user content.

The minimum agent-facing projection contains only the current `memory_id`,
`version_id`, text, optional summary and relationships, evidence IDs, capture
type, and timestamps. It excludes account keys, storage paths, idempotency
keys, superseded versions, and direct mutation authority.

Migrating the Memory & Policy Service to this schema is tracked by `linger-4sp`;
it can proceed independently and does not block the initial Librarian path.

### 7.3 Implemented benchmark selection

1. Version an Alice query set covering names, exact quotations, events,
   paraphrases, themes, weak or absent evidence, and boundary failures.
2. Run every query against the same eligible chapter boundary using:
   - bounded direct canonical reads;
   - BM25 lexical retrieval;
   - embedding-based semantic retrieval;
   - hybrid BM25 plus semantic fusion and deduplication without reranking; and
   - the same hybrid candidates with reranking.
3. Require zero forbidden-chapter exposure and exact canonical evidence
   resolution from every qualifying approach.
4. Measure retrieval recall, citation precision, p95 latency, token use, and
   monetary cost with versioned configurations. Measure the model's
   evidence-strength decisions in live release validation.
5. Among strategies that pass safety and citation-resolution checks, compute
   `quality_score = (2 × recall + precision) / 3`. Treat scores within `0.02`
   of the best as equivalent, then prefer lower p95 latency, fewer evidence
   words, and lower local monetary cost. Preserve each individual metric in
   the report. Evidence words are not provider token usage.

### 7.4 Measured selection

The frozen 12-case Alice set produced these five-repeat warm-query results. The
reported precision is retrieval-candidate precision before the common
Librarian evidence-strength judge; final user-visible citation precision is
measured in the end-to-end evaluation.

These figures describe the saved benchmark report and its recorded grader.
Its strength-support accuracy is a coverage-derived label, not a model judgment.
The executable benchmark requires full containment of each gold source range
and weights recall and precision 2:1 for selection. Reproduce that command for
results under the current grading contract.

| Strategy | Recall | Candidate precision | Strength-support accuracy | p95 latency | Mean evidence words |
|---|---:|---:|---:|---:|---:|
| Direct canonical reads | 50.0% | 16.3% | 66.7% | 3.2 ms | 402 |
| BM25 | 75.0% | 28.3% | 91.7% | 3.1 ms | 1,518 |
| Semantic embeddings | 79.2% | 33.3% | 100% | 3.0 ms | 1,433 |
| Hybrid without reranking | 79.2% | 30.0% | 100% | 2.9 ms | 1,535 |
| **Hybrid with reranking** | **91.7%** | **82.6%** | **91.7%** | **461.1 ms** | **595** |

The selected local stack is BM25S, FastEmbed
`BAAI/bge-small-en-v1.5`, reciprocal-rank fusion with `k = 60`, and FastEmbed
cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2`. Derived indexes are cached by
immutable book revision and exact chapter ceiling. The first local model and
index initialization is excluded from warm p95 and remains visible as a
deployment warm-up cost. These measurements evaluated Librarian's
exact-question grounding path. At that time, Serendipity used the bounded
diversified direct-read control. Current Muse grounding and Serendipity book
search share the judged hybrid operation described in Section 4.4. The
historical grounding results do not measure broader connection quality, which
Serendipity evaluates separately.

### 7.5 Historical live end-to-end validation

On August 17, 2026, the then-frozen 12-case set was run through the reader-confirmed
application boundary, selected hybrid retriever, configured Librarian strength
judge, Muse, Provenance, and deterministic release validation with
`openai:gpt-5.6-luna`. The report is versioned at
[`../../evals/librarian/live-report.json`](../../evals/librarian/live-report.json).

| Metric | Result | Target | Outcome |
|---|---:|---:|---|
| Final evidence recall | 91.7% | at least 90% | Pass |
| Final citation precision | 100% | at least 95% | Pass |
| Evidence-strength accuracy | 91.7% | at least 90% | Pass |
| Answerable-case release rate | 100% | at least 90% | Pass |
| Forbidden-chapter exposure | 0 | 0 | Pass |
| Exact citation resolution | 100% | 100% | Pass |
| End-to-end latency | 13.7 s mean; 27.9 s p95 | budget TBD | Measured |

The current tool binds the original reader message and then plans focused
queries as described in Section 4.4; the historical report predates that path.
The saved report records unavailable usage, not zero usage. Current
`live_validation._usage` reads recorded agent-exchange usage or the SDK usage
property, so the old report does not establish a current provider limitation.
No new provider evaluation was performed for this documentation update.

## 8. Decisions and open questions

### 8.1 Resolved

| Decision | Resolution |
|---|---|
| First book | Project Gutenberg ebook 11 |
| Upstream source | Immutable downloaded text with a fixed SHA-256 |
| Registered retrieval corpora | Five books with exact-layout Markdown chapters or sections; Alice's initial corpus has twelve chapters |
| Routing metadata | Compact, validated JSON front matter |
| Agent catalogue | Generated metadata-only JSON projection |
| Database or index as source of truth | No |
| Initial retrieval baseline | Agentic catalogue inspection and bounded chapter reads |
| Retrieval strategy selection | Reranked hybrid won the mandatory five-way comparison |
| Reading progress | Explicit completed chapters persist per account and work; session carry handles corrections; inferred and exact-passage permissions remain outside the durable store |
| Metadata as evidence | No; only canonical chapter or section bodies are authoritative |
| Ambiguous boundary | Typed clarification after optional private localization; no answer-evidence search is authorized |
| Completed retrieval | Typed result with sufficient, weak, or none strength |
| Weak result | Includes exact evidence details plus limitations |
| Sufficient result shown to Muse | Replaces only `strength_reason` with a fixed application sentence; Serendipity and recorded assessments keep the original reason |
| Assessment labels | Temporary `E1`, `E2` labels map back to canonical IDs after validation |
| Answer-list experiment | Reverted on October 12; current Librarian has four assigned skills and returns evidence, strength, reason, and limitations |
| Offline cue and retention experiments | Opt-in only; production searches passage text and retains four candidates per planned query |
| Corpus identity | Stable work ID plus immutable source-revision ID |
| Evidence identity | Book version + chapter + canonical source lines |
| Derived windows | 350-word target with 60-word overlap; whole paragraphs stay inside a canonical unit |
| Initial thresholds | Public search uses 0.5 semantic and reranker cutoffs; private judgment retains its bounded candidate pool below those cutoffs |
| Candidate limits | Public retrieval fuses at most 15; private retrieval scores up to 20 per query. Gathering retains four per planned query in routed books, two per fallback query per book, and at most 20 merged per book. Production tools return at most 5 selected records |
| Selected local models | `BAAI/bge-small-en-v1.5` embedding + `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder |
| Hybrid fusion | RRF with `k = 60`; public shortlist uses 50% overlap deduplication. Private selection interleaves lexical, fused, semantic, and reranked streams. Gathering removes duplicate IDs and fully contained windows, preserving partial overlaps |
| Historical release quality | August 17 report: 91.7% recall, 100% precision, 91.7% strength accuracy, zero measured spoiler exposure on 12 Alice cases; not current multi-book validation |

### 8.2 Open

| Decision | Status |
|---|---|
| Partial-current-chapter boundaries | General scene or line ceilings remain undefined. Exact canonical paragraph grants are supported without chapter progress. |
| Latency and cost budgets | Approve budgets for the current runtime; historical timings and missing usage do not establish current operating limits |
