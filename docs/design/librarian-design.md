# Librarian Subsystem Design

Status: **Two-phase Alice Librarian implemented; broader evaluation and corpus expansion remain**

This document defines the retrieval-neutral book corpus and the typed boundary
of the Librarian implementation. It elaborates on the Librarian
responsibilities and safeguards in [`../specification.md`](../specification.md).

### Progress snapshot

Beads is the durable source of truth; this table is its human-readable design
projection as of 28 August 2026.

| Track | Progress | Current state | Beads |
|---|---:|---|---|
| Design foundation | 4 of 4 (100%) | Corpus lifecycle generalized; Anthropic-inspired memory schema adopted; Librarian response union defined; Markdown and HTML aligned | `linger-tz2`, `linger-5gj`, `linger-hfo`, `linger-7bm` |
| Initial Librarian implementation | 6 of 6 slices (100%) | Corpus, boundary, retrieval, Muse handling, five-way strategy selection, and live end-to-end validation are complete | `linger-ibq` |
| Two-phase spoiler boundary | 1 of 1 implementation slice (100%) | Full-work private inference returns a validated content-free candidate or focused clarification before the second bounded search | `linger-lfh` |
| Muse-initiated routing | 1 of 1 implementation slice (100%) | Application no longer routes eagerly; Muse calls a confidence-gated `librarian_route` tool only when a request appears book-dependent | |
| Memory schema adoption | 1 of 2 stages (50%) | Design adopted; Memory & Policy Service migration is ready and independent of Librarian | `linger-5gj`, `linger-4sp` |

The benchmark selected spoiler-bounded BM25 plus semantic retrieval,
reciprocal-rank fusion, overlap deduplication, and local cross-encoder reranking.
All five configurations passed the zero-forbidden-exposure and exact-resolution
gates. The selected retrieval path reached 91.7% evidence recall and 82.6%
candidate precision; the latter is diagnostic because the Librarian judge still
filters candidates before Muse receives final evidence. The live 12-case
Librarian → Muse → Provenance release evaluation then reached 91.7% final
evidence recall, 100% citation precision, and zero spoiler exposure.

## 1. Purpose and scope

The subsystem has two deliberately separate flows:

1. **Offline corpus preparation** converts a verified source book into
   canonical, human-readable Markdown chapters and a derived metadata-only
   catalogue.
2. **Online retrieval** uses a request-scoped reading boundary to either ask one
   focused clarification or inspect only eligible chapters and return a typed
   evidence result to Muse.

The current vertical slice implements both flows for Project Gutenberg ebook
11. Direct canonical reads remain the benchmark control; the measured
production path uses bounded BM25 and local embeddings, reciprocal-rank fusion,
overlap deduplication, and a local cross-encoder reranker before the independent
Librarian evidence-strength decision.

### 1.1 Responsibilities

Librarian may:

- privately search a complete authorised work to locate reader-known events;
- propose a request-scoped candidate ceiling with confidence and supporting locations;
- inspect compact metadata for chapters inside the current request's boundary;
- choose and read relevant canonical chapter files;
- use later keyword, semantic, or hybrid indexes when available;
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
Extract 12 chapters deterministically
                    ↓
Canonical Markdown chapters
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
User request + transient conversation context
                    ↓
Reading declaration or full-title answer?
        └─ Shared identity resolver → registered identity only
                    ↓
Explicit completion for the selected book in this request?
        ├─ yes → Application validates chapter ceiling ────────────┐
        └─ no  → Muse judges book intent                           │
                    ↓ (lookup needed)                             │
                 librarian_route                                  │
                    ↓                                             │
                 Shared identity resolver                         │
                 (catalogue cues only if no name signal)          │
                    ├─ unresolved → Exact identity clarification   │
                    ├─ no match → Ask for title if needed          │
                    └─ resolved work                              │
                           ↓                                      │
                 Private boundary inference                       │
                 (current Line + eligible account memories        │
                  + full-work candidates)                         │
                           ↓                                      │
                 Application validates candidate ceiling          │
                    ├─ uncertain → Exact boundary clarification    │
                    └─ validated ─────────────────────────────────┤
                                                                  ↓
                                                  Eligible catalogue only
                                                                  ↓
                                                  Bounded evidence search
                                                                  ↓
                                                  Rerank candidate evidence
                                                                  ↓
                                                  Judge evidence strength
                                                                  ↓
                                                  Typed result to Muse
```

The benchmark search indexes supply candidate passages between catalogue
filtering and chapter reading. They do not change the boundary or the source of
truth, and non-selected indexes need not remain in the production path.

### 2.3 Component ownership

| Component | Responsibility |
|---|---|
| Gutenberg source | Immutable upstream text and download provenance |
| Corpus processor | Verifies the source, extracts exact chapter bodies, renders initial Markdown, and checks integrity |
| Canonical chapter files | Store authoritative chapter bodies and routing front matter in reviewable text files |
| Catalogue builder | Projects canonical front matter into a body-free routing catalogue |
| Book registry | Stores human-reviewed titles, IDs, authors, and classified aliases; deterministic code checks collisions and resolves names |
| Muse | Judges when a request depends on a book, calls `librarian_route`, responds to clarification outcomes, and drafts replies using granted evidence |
| Application boundary | Supplies the original reader message and access scope, resolves identity, validates explicit or inferred ceilings, and enforces reply release |
| Librarian agent | Infers a private candidate ceiling, then judges the answerability of separately retrieved bounded evidence |
| Retrieval and reranker tools | Search and order only candidates already inside the validated scope |
| Sculptor | Optionally proposes semantic metadata offline for human review; deterministic tooling builds the catalogue. Runtime Sculptor handles memory curation |
| Provenance | Runs safety preflight and reviews Muse's draft; cannot grant retrieval access or release a reply itself |
| Serendipity | Proposes connections; has no book-registration or identity-resolution responsibility |

## 3. Offline corpus preparation

### 3.1 Checked-in artifacts

The first corpus is:

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

The reusable lifecycle accepts a source-specific adapter. Alice uses
`src.linger.corpus.alice`; a future chapter-based book supplies its own adapter
without copying rendering, catalogue, or integrity code:

```bash
# One-time creation; refuses to overwrite any existing corpus artifact
uv run python -m src.linger.corpus.book src.linger.corpus.alice init

# Regenerate only the derived catalogue from canonical front matter
uv run python -m src.linger.corpus.book src.linger.corpus.alice build-catalog

# Read-only source, chapter, front-matter, and catalogue verification
uv run python -m src.linger.corpus.book src.linger.corpus.alice check
```

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

The benchmark starts with 450-token paragraph windows and 75-token overlap,
always contained within one chapter. These are derived-index defaults, not part
of the canonical chapter format, and are tuned during comparison.

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

The application no longer routes every turn eagerly. Muse decides whether a
request depends on a specific book and, only then, calls the argument-less
`librarian_route` tool; the application supplies the exact current reader
message from a turn-scoped context variable, so Muse cannot substitute its own
text. Explicit reading declarations and `route_work` share the deterministic
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
to strong support. Without name signals, distinctive catalogue phrases and
broad contextual agreement can still provide strong candidates, while common
catalogue words remain weak. The [registration guide](../book-registration.md)
describes the alias policy, collision checks, and agent responsibilities.

A resolved work enters the private boundary phase described below. If a
`NoMatch` leaves a book-dependent request unresolved, Muse asks for its full
title and author; otherwise it can continue personal reflection. For identity
and boundary clarifications from `librarian_route`, application code releases
the validated question after Provenance passes. Muse need not copy it verbatim.
Evidence declarations and non-route tool calls still block release.
A route grants a scope, not source text. Muse calls `librarian_search` with the
returned `work_id` and `book_version_id`. A chapter route supplies
`max_chapter_inclusive` for `reading_boundary`; a passage route requires
`reading_boundary=None` and permits only its exact paragraph IDs. A routed
result also names the deterministic `selection_basis` that identified the
work — `resolved_book_identity`, `distinctive_cue`, or `session_selection`.

### 4.2 Input and output contracts

The boundary phase runs exactly when `librarian_route` matched a work; an
explicit reader-confirmed ceiling is authoritative and terminal for the
request and never enters this phase. Once a work is routed, application code
hands off to the private boundary phase. It receives the current Line,
a bounded set of strongly routed account-scoped memories, original earlier
reader statements from the same session, and full-work retrieval candidates.
With earlier reader statements, candidates are narrowed to canonical paragraphs
and the phase can grant exact passages without a completed chapter. See
[Session-supported exact passages](session-passage-design.md). The chapter
inference example below omits earlier reader statements:

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

Only the private Librarian boundary agent sees the memory and candidate text.
Its accepted output contains no passage text:

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
memory-supported candidate receives a request-scoped retrieval grant. Muse then
supplies the exact question for the separate bounded evidence phase:

```json
{
  "request_id": "libreq_01K2...",
  "query": "Why does Alice struggle to explain who she is?",
  "work_id": "pg11",
  "book_version_id": "pg11-v01b38ea4",
  "reading_boundary": {
    "chapter_number": 5,
    "chapter_state": "completed"
  },
  "access_scope": {
    "allowed_book_version_ids": ["pg11-v01b38ea4"]
  },
  "options": {
    "retrieval_score_threshold": 0.5,
    "max_final_evidence": 5
  }
}
```

`access_scope` is created by trusted application code, never copied from model
output. Thresholds may be overridden by evaluated configuration, but no agent
may lower them or enlarge scope.

### 4.3 Boundary enforcement and clarification

Boundary inference and evidence retrieval are separate calls:

1. The inference search may inspect the complete immutable work, but its
   passages remain private and never enter the turn evidence ledger.
2. Librarian declares `memory_supported` or `line_only` and selects only input
   memory IDs plus content-free supporting evidence IDs and locations.
3. Application code derives the ceiling from those trusted records and rejects
   invented memory or evidence IDs, a mismatched work or revision, an invalid
   basis, and inconsistent chapters.
4. Line-only curiosity, confidence below `0.75`, or any ambiguity yields an exact clarification; the
   release validator rejects a book answer or tool call in its place.
5. A validated candidate enables a new search whose scope is clamped to the
   inferred ceiling. No boundary is persisted to later requests.

At chapter granularity:

- Chapter 5 `completed` permits Chapters 1 through 5.
- Chapter 5 `started` permits Chapters 1 through 4.
- Missing, conflicting, or ambiguous state returns a clarification without
  opening the catalogue or running retrieval.

During the second phase, post-boundary catalogue entries and chapter bodies
must not reach the evidence judge, Muse, a bounded index, a reranker, or any
downstream answer context. The private first-phase Librarian is the sole
exception and has localization authority, not disclosure authority. Reading
progress is not durable memory; it is resolved again for each book-related
request.

Clarification is a distinct response type, not a weak or empty retrieval
result:

```json
{
  "kind": "clarification",
  "request_id": "libreq_01K2...",
  "clarification_id": "clar_01K2...",
  "reason_code": "current_chapter_state_ambiguous",
  "question": "Have you finished Chapter 5, or have you only started it?",
  "expected_answer": {
    "type": "one_of",
    "values": ["completed", "started"]
  }
}
```

A clarification contains no evidence, retrieval score, or evidence-strength
label because no search occurred. Muse presents the focused question and sends
the answer through the same trusted boundary validator.

General partial-current-chapter ceilings remain unsupported. Exact canonical
paragraph IDs support the narrower session-passage permission described in
[Session-supported exact passages](session-passage-design.md), without implying
completion of the chapter or permission for neighboring text.

### 4.4 Retrieval, fusion, and deduplication

Direct bounded chapter selection is the control. The benchmark adds only
disposable indexes:

```text
Validated request
        ↓
Filter catalogue and indexes to eligible chapters
        ↓
Keyword search (up to 10) + semantic search (up to 10, score ≥ 0.5)
        ↓
Fuse by evidence identity and remove duplicate/overlapping windows
        ↓
At most 15 permitted candidates
        ↓
Reranker orders candidates by query relevance
        ↓
Resolve final passages to exact canonical chapter lines
        ↓
Librarian judges the evidence set: sufficient, weak, or none
```

The restriction is applied before search, not after retrieval. A duplicate hit
keeps one canonical evidence record and records both retrieval methods and
their scores. Strongly overlapping neighbouring windows are merged only after
resolving their exact canonical range; text is never paraphrased during merge.

### 4.5 Reranking versus evidence strength

These are separate decisions:

| Stage | Owner | Question answered | Output |
|---|---|---|---|
| Retrieval threshold | Retrieval tool | Is this candidate similar enough to keep? | Candidate kept or removed |
| Reranking | Reranker tool called by Librarian | Which individual candidate best matches this query? | Ordered candidate list |
| Evidence-strength decision | Librarian agent | Can the eligible evidence set actually answer Muse's request? | `sufficient`, `weak`, or `none` |

A high retrieval or reranker score does not prove that the passage answers the
question. It may match the same words while missing the requested relationship
or explanation. Conversely, `weak` evidence still includes its full evidence
details so Muse can explain the limitation instead of losing context.

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
└────────────────────── immutable book-version ID
```

The evidence record also carries the full source hash. A shortened-hash
collision is a hard failure. Candidate-window IDs may exist inside a derived
index, but Muse and Provenance receive the final canonical line-based evidence
ID.

### 4.7 Result contract

When retrieval runs, Librarian returns `kind: result`. This is distinct from a
clarification. A sufficient result looks like:

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
      "chapter_title": "Advice from a Caterpillar",
      "source_sha256": "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e",
      "source_lines": [974, 981],
      "text": "“I can’t explain _myself_, I’m afraid, sir,” said Alice, “because I’m\nnot myself, you see.”\n\n“I don’t see,” said the Caterpillar.\n\n“I’m afraid I can’t put it more clearly,” Alice replied very politely,\n“for I can’t understand it myself to begin with; and being so many\ndifferent sizes in a day is very confusing.”",
      "retrieval": {
        "methods": ["keyword", "semantic"],
        "keyword_rank": 2,
        "semantic_score": 0.82,
        "reranker_rank": 1,
        "reranker_score": 0.91
      }
    }
  ],
  "limitations": []
}
```

For weak evidence, the same evidence details are present:

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
├── ClarificationRequest   kind = clarification; retrieval did not run
├── RetrievalResult       kind = result; completed with sufficient/weak/none
└── RetrievalFailure      kind = failure; system could not complete safely
```

A retrieval failure is reserved for unavailable or corrupt dependencies, an
unresolvable evidence ID, or another safe-completion failure. It is not used for
ordinary `no_evidence`.

### 4.8 Failure behaviour

Retrieval fails closed when the boundary or evidence location cannot be
validated. Once a production strategy is selected, search or reranking failures
may degrade to direct chapter reads only when those reads remain inside the same
validated scope. The failure response includes a stable error code and
retryability flag, but no unvalidated excerpt.

### 4.9 Online verification

Before the online path is considered complete, tests must cover:

- the clarification/result/failure union and Muse handling for each branch;
- Chapter 5 `started` exposing only Chapters 1–4 and `completed` exposing 1–5;
- catalogue filtering before agent exposure;
- direct chapter selection for names, events, quotations, and themes;
- later chapters never reaching tools or model context;
- exact quotation and source-location resolution;
- sufficient, weak, and absent evidence behaviour, including evidence details
  on weak results;
- duplicate fusion and stable canonical evidence IDs;
- retrieval/reranker thresholds not being confused with evidence strength;
- prompt instructions in book text remaining untrusted data; and
- every degraded path retaining the same scope.

## 5. Downstream integration

Muse switches on `kind` before it drafts anything:

| Librarian response | Muse action |
|---|---|
| `clarification` | Ask the supplied focused question; do not draft a book answer and do not treat it as weak evidence |
| `result` + `sufficient` | Draft an evidence-grounded candidate and cite only returned evidence IDs |
| `result` + `weak` | Include the returned evidence context, clearly state the limitation, and avoid unsupported conclusions |
| `result` + `none` | Say the eligible material did not provide support; never imply later chapters were searched |
| `failure` | Produce no evidence-based draft; orchestration chooses retry or an application-authored safe message |

A Librarian result is evidence for Muse, not permission to display a response:

```text
Librarian evidence bundle
      ↓
Muse drafts typed candidate response
      ↓
Provenance reviews complete response and cited evidence
      ↓
Application validates exact quotations, source locations,
account scope, and request-scoped spoiler boundary
      ↓
Release or application-authored safe decline
```

Muse should distinguish direct evidence from interpretation and state when the
eligible material is weak or silent. Provenance independently determines
whether the resulting response is supported and spoiler-safe.

## 6. Initial configuration

The canonical corpus has no retrieval tuning configuration. The required
retrieval benchmark begins with inexpensive, overrideable defaults:

```yaml
derived_windows:
  target_tokens: 450
  overlap_tokens: 75
  cross_chapter: false

retrieval:
  keyword_candidates: 10
  semantic_candidates: 10
  semantic_score_threshold: 0.5
  max_reranker_candidates: 15
  reranker_score_threshold: 0.5
  max_final_evidence: 5
```

The two `0.5` thresholds are starting values, not evidence strength. Candidate
counts, latency, cost, models, and thresholds must be tuned with the Alice eval
set. Direct bounded chapter reads remain the no-index baseline.

## 7. Implementation sequence

### 7.1 Initial product path

| Order | Slice | Status | Deliverable | Beads |
|---:|---|---|---|---|
| 1 | Offline corpus and hardening | Complete | Verified immutable source, revision-aware canonical chapters, derived catalogue, reusable lifecycle, and deterministic checks | `linger-tz2` |
| 2 | Contracts and spoiler boundary | Complete | Typed request/response models and trusted completed/started/ambiguous chapter enforcement before corpus access | `linger-ibq.1` |
| 3A | Bounded direct evidence retrieval | Complete | Canonical reads, thresholds, no-match behavior, exact line-range evidence IDs, pre-read spoiler filtering, and independent strength judgement | `linger-ibq.2` |
| 3B | Muse response integration | Complete | Separate handling for clarification, sufficient, weak, none, and failure | `linger-ibq.3` |
| 4 | Retrieval benchmark and selection | Complete | Five versioned configurations compared; reranked hybrid selected and implemented | `linger-ibq.5` |
| 5 | End-to-end validation | Complete | Selected strategy, spoiler suppression, evidence resolution, failures, safe degradation, live strength judgement, and Muse/Provenance release measured against the full versioned set | `linger-ibq.4` |

Slices 3A and 3B may proceed in parallel after the shared contract and boundary
slice is complete. Slice 4 can run after the direct-read control exists while
Muse integration proceeds independently. The epic closes only after Slice 5
passes with the selected retrieval strategy.

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

### 7.3 Required retrieval benchmark and selection

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
4. Measure evidence recall, citation precision, evidence-strength accuracy,
   p95 latency, token use, and monetary cost with versioned configurations.
5. Select the configuration with the strongest evidence quality. When results
   fall within a predeclared quality-equivalence margin, prefer lower p95
   latency, then lower token use and monetary cost. Report every metric rather
   than hiding trade-offs in one blended score.

### 7.4 Measured selection

The frozen 12-case Alice set produced these five-repeat warm-query results. The
reported precision is retrieval-candidate precision before the common
Librarian evidence-strength judge; final user-visible citation precision is
measured in the end-to-end evaluation.

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
deployment warm-up cost. This selection applies to Librarian's exact-question
grounding path. Serendipity's deliberately multi-chapter connection discovery
keeps the bounded diversified direct-read control until connection retrieval
has its own evaluation; it must not silently inherit a strategy optimized for a
different objective.

### 7.5 Live end-to-end validation

The complete frozen 12-case set was run through the reader-confirmed
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

Muse passes the reader's book question to Librarian without paraphrasing. A
bounded output-only retry repairs citation-copy metadata before Provenance;
deterministic validation still fails closed if an evidence ID, location, or
visible exact quote does not resolve. The configured provider did not expose
token usage through the current SDK result, so token and monetary cost remain
unreported rather than being estimated.

## 8. Decisions and open questions

### 8.1 Resolved

| Decision | Resolution |
|---|---|
| First book | Project Gutenberg ebook 11 |
| Upstream source | Immutable downloaded text with a fixed SHA-256 |
| Canonical retrieval corpus | Twelve exact-layout Markdown chapter files |
| Routing metadata | Compact, validated JSON front matter |
| Agent catalogue | Generated metadata-only JSON projection |
| Database or index as source of truth | No |
| Initial retrieval baseline | Agentic catalogue inspection and bounded chapter reads |
| Retrieval strategy selection | Reranked hybrid won the mandatory five-way comparison |
| Reading progress | Not persisted; boundary is inferred or clarified per request |
| Metadata as evidence | No; only canonical chapter bodies are authoritative |
| Ambiguous boundary | Typed clarification; retrieval does not run |
| Completed retrieval | Typed result with sufficient, weak, or none strength |
| Weak result | Includes exact evidence details plus limitations |
| Corpus identity | Stable work ID plus immutable source-revision ID |
| Evidence identity | Book version + chapter + canonical source lines |
| Initial derived windows | 350 words (approximately 450 tokens) with 60-word overlap (approximately 75 tokens), never crossing chapters |
| Initial thresholds | 0.5 for semantic candidate and reranker scores; overrideable |
| Candidate limits | 10 keyword + 10 semantic, at most 15 reranked, at most 5 returned |
| Selected local models | `BAAI/bge-small-en-v1.5` embedding + `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder |
| Hybrid fusion | Reciprocal-rank fusion with `k = 60`, followed by 50% source-range overlap deduplication |
| Live release quality | 91.7% evidence recall, 100% citation precision, 91.7% strength accuracy, and zero spoiler exposure on the complete 12-case set |

### 8.2 Open

| Decision | Status |
|---|---|
| Partial-current-chapter boundaries | General scene or line ceilings remain undefined. Exact canonical paragraph grants are supported without chapter progress. |
| Latency and cost budgets | End-to-end mean and p95 are measured; set product budgets and obtain provider token/cost reporting in `linger-cnx` |
