# Librarian Subsystem Design

Status: **Draft implementation design**

This document defines the retrieval-neutral book corpus and the boundaries for
the future Librarian implementation. It elaborates on the Librarian
responsibilities and safeguards in [`../specification.md`](../specification.md).

## 1. Purpose and scope

The subsystem has two deliberately separate flows:

1. **Offline corpus preparation** converts a verified source book into
   canonical, human-readable Markdown chapters and a derived metadata-only
   catalogue.
2. **Online retrieval** uses a request-scoped reading boundary to inspect the
   eligible catalogue, open relevant chapters just in time, and return cited
   source evidence to Muse.

The current vertical slice implements the first flow for Project Gutenberg
ebook 11. The chapter files also support direct agentic retrieval now. BM25
paragraph windows, embeddings, hybrid retrieval, fusion, and reranking remain
optional derived capabilities; their exact design is not yet fixed.

### 1.1 Responsibilities

Librarian may:

- inspect compact metadata for chapters inside the current request's boundary;
- choose and read relevant canonical chapter files;
- use later keyword, semantic, or hybrid indexes when available;
- judge whether the retrieved evidence is sufficient, weak, or absent; and
- return exact source evidence and resolvable locations to Muse.

Librarian may not:

- choose, persist, or widen the user's reading boundary;
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
Optional later indexes
(BM25 paragraph windows, embeddings, or hybrid)
```

The immutable text file remains the upstream source. The checked-in Markdown
chapters are the canonical retrieval corpus. The catalogue and any future
search indexes are disposable projections that must be regenerable from those
chapters.

### 2.2 Online retrieval flow

```text
User request + transient conversation context
                    ↓
Muse infers the temporary reading boundary
or asks where the user stopped
                    ↓
Application validates the typed boundary
                    ↓
Eligible chapter catalogue only
                    ↓
Librarian selects and reads relevant chapters
                    ↓
Exact cited evidence returned to Muse
```

An optional search index may later supply candidate passages between catalogue
filtering and chapter reading. It does not change the boundary or the source of
truth.

### 2.3 Component ownership

| Component | Responsibility |
|---|---|
| Gutenberg source | Immutable upstream text and download provenance |
| Corpus processor | Verifies the source, extracts exact chapter bodies, renders initial Markdown, and checks integrity |
| Canonical chapter files | Store authoritative chapter bodies and routing front matter in reviewable text files |
| Catalogue builder | Projects canonical front matter into a body-free routing catalogue |
| Muse | Infers or clarifies a temporary reading boundary and passes it as a typed request constraint |
| Application boundary | Validates and enforces Muse's declared scope without choosing or persisting it |
| Librarian | Selects eligible chapters, retrieves evidence, and judges evidence strength |
| Sculptor | May later propose reviewed routing-metadata improvements; it never changes canonical chapter bodies |
| Muse and Provenance | Draft and review the eventual response; neither treats routing metadata as evidence |

## 3. Offline corpus preparation

### 3.1 Checked-in artifacts

The first corpus is:

```text
data/gutenberg/
└── alice-in-wonderland.txt            # immutable downloaded source

data/corpus/alice-in-wonderland/
├── catalog.json                       # derived, metadata only
└── chapters/
    ├── 01-down-the-rabbit-hole.md     # canonical
    ├── 02-the-pool-of-tears.md
    └── ...
```

The source SHA-256 is fixed in the processor and recorded in every chapter's
front matter. A changed source fails validation and requires deliberate review;
the processor does not silently accept a new edition.

### 3.2 Deterministic extraction

The Alice processor verifies:

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
  "document_id": "pg11",
  "chapter_id": "pg11-ch01",
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

- `chapter_id`, `chapter_number`, and `title` identify and order the chapter;
- `routing_description`, `characters`, `locations`, and `retrieval_cues` help
  an agent decide whether to open it; and
- counts, paths, ranges, and hashes support deterministic integrity checks.

Routing metadata is navigation help, not evidence. Quotations and factual book
claims must resolve to the chapter body.

### 3.4 Metadata-only catalogue

`catalog.json` contains document identity and a projection of each chapter's
routing metadata:

```json
{
  "schema_version": 1,
  "document_id": "pg11",
  "title": "Alice's Adventures in Wonderland",
  "author": "Lewis Carroll",
  "source_path": "data/gutenberg/alice-in-wonderland.txt",
  "source_sha256": "01b38e...",
  "chapter_count": 12,
  "chapters": [
    {
      "chapter_id": "pg11-ch01",
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

The processor exposes three explicit operations:

```bash
# One-time creation; refuses to overwrite any existing corpus artifact
uv run python -m src.linger.corpus.alice init

# Regenerate only the derived catalogue from canonical front matter
uv run python -m src.linger.corpus.alice build-catalog

# Read-only source, chapter, front-matter, and catalogue verification
uv run python -m src.linger.corpus.alice check
```

After initial creation, routing metadata may be edited in the canonical chapter
files and the catalogue rebuilt. The integrity check still requires every
chapter body and deterministic provenance field to match the immutable source.

### 3.6 Verification

Automated checks cover:

- immutable-source hashing;
- twelve ordered story chapters with expected titles and line ranges;
- exclusion of contents, illustration, Gutenberg wrapper, and `THE END`;
- exact preservation of source layout and code points;
- deterministic initial rendering and overwrite refusal;
- valid front matter, stable identifiers, checksums, and word counts;
- a metadata-only catalogue in canonical chapter order;
- catalogue rebuilding without changing chapter files;
- detection of missing, unexpected, stale, or tampered files; and
- checked-in corpus freshness.

### 3.7 Optional derived indexes

Future retrieval experiments may derive paragraph windows from canonical
chapter bodies for BM25, embeddings, or hybrid search. Any such index must:

- be fully regenerable and never become the source of truth;
- retain `document_id`, `chapter_id`, and a resolvable source location;
- never cross a chapter boundary;
- preserve exact body text for evidence and quotation validation;
- record its chunking, embedding, and ranking versions; and
- apply the request boundary before forbidden text reaches a model or reranker.

No chunk size, overlap, embedding model, threshold, fusion method, or reranker
is selected until evaluation shows that it improves on direct chapter reads.

## 4. Online retrieval flow

### 4.1 Current retrieval-neutral path

The canonical corpus supports the following minimal Librarian path without a
database or search index:

1. Muse infers a temporary boundary from the current message and transient
   conversation context.
2. If the stopping point is unclear, Muse asks a focused clarification before
   book retrieval.
3. Muse returns a typed, request-scoped constraint such as the last completed
   chapter and, later, an optional position within the current chapter.
4. Application code validates the declared chapter against the corpus and
   filters the catalogue before Librarian sees it.
5. Librarian uses the eligible routing metadata to choose chapter files and
   reads only those bodies.
6. Librarian returns exact evidence from the canonical body with enough source
   information for deterministic citation validation.

Reading progress is not account data, policy state, or durable memory. Linger
resolves the boundary again for each book-related request. Application code
validates and enforces Muse's declared boundary; it does not infer one itself.

### 4.2 Boundary enforcement

A missing, invalid, or ambiguous boundary fails closed and leads to
clarification. Post-boundary catalogue entries and chapter bodies must not be
shown to Librarian, Muse, an optional index, a reranker, or downstream model
context.

If a future boundary includes a position within the current chapter, the
application must define and validate a resolvable location before partial-
chapter retrieval is enabled. Until then, chapter-level scope is the supported
unit.

### 4.3 Optional search path

Direct chapter selection is the baseline. A later search path may add:

```text
Eligible catalogue
        ↓
BM25 paragraph windows and/or embeddings
        ↓
Optional fusion and reranking
        ↓
Canonical chapter text resolution
        ↓
Evidence bundle
```

Search results are candidates, not evidence by themselves. Returned text must
resolve back to the canonical Markdown body, and failure of an optional index
must never widen the boundary. Exact tool inputs, evidence identifiers,
candidate limits, and evidence-strength types remain open until the baseline is
evaluated.

### 4.4 Evidence and failure behaviour

Librarian should distinguish:

- `sufficient`: the eligible source directly supports an answer;
- `weak`: relevant source exists but does not fully support the claim; and
- `none`: no useful evidence was found inside the eligible scope.

These labels are advisory. Provenance still reviews Muse's complete draft, and
application code still validates exact quotations and source locations.

Retrieval fails closed when the boundary or evidence location cannot be
validated. Optional search or reranking failures may degrade to direct chapter
reads only when those reads remain inside the same validated scope.

### 4.5 Online verification

Before the online path is considered complete, tests must cover:

- boundary inference and clarification hand-offs;
- catalogue filtering before agent exposure;
- direct chapter selection for names, events, quotations, and themes;
- later chapters never reaching tools or model context;
- exact quotation and source-location resolution;
- sufficient, weak, and absent evidence behaviour;
- prompt instructions in book text remaining untrusted data; and
- every degraded path retaining the same scope.

## 5. Downstream integration

The Librarian result is evidence for Muse, not permission to display a response:

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

The implemented corpus has no retrieval tuning configuration. Its fixed
contract is the source path, source hash, twelve expected chapters, canonical
output path, and schema version defined by the processor.

Chunk size, overlap, candidate counts, embedding thresholds, fusion, reranking,
and evidence limits are intentionally absent. Add them only with the retrieval
implementation that uses them and evidence that the chosen defaults are useful.

## 7. Implementation sequence

### 7.1 Completed offline vertical slice

1. Verify the immutable Gutenberg #11 source.
2. Extract and validate its twelve exact-layout chapter bodies.
3. Create canonical Markdown chapter files with compact JSON front matter.
4. Generate the metadata-only catalogue.
5. Check source, body, metadata, and catalogue integrity deterministically.

### 7.2 Next online vertical slice

1. Define Muse's typed request-scoped reading-boundary hand-off.
2. Validate the declared boundary against the catalogue.
3. Expose eligible chapter metadata and bounded chapter reads to Librarian.
4. Return exact canonical text and resolvable locations to Muse.
5. Validate quotations after Provenance approval.
6. Exercise clarification and spoiler-suppression paths end to end.

### 7.3 Retrieval experiments, only if needed

1. Create a small Alice query set covering names, exact quotations, events,
   paraphrases, themes, and boundary failures.
2. Measure direct chapter reads as the baseline.
3. Compare BM25 paragraph windows, embeddings, and hybrid retrieval as derived
   indexes.
4. Add only the smallest approach that materially improves retrieval quality,
   latency, or context use while preserving citation resolution.

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
| Reading progress | Not persisted; boundary is inferred or clarified per request |
| Metadata as evidence | No; only canonical chapter bodies are authoritative |

### 8.2 Open

| Decision | Status |
|---|---|
| Librarian tool and result contracts | Define in the online vertical slice |
| Exact evidence identifiers and within-chapter locations | Evaluate with citation validation |
| Partial-current-chapter boundaries | Define only when resolvable positions are available |
| BM25 paragraph-window rules | Optional; evaluate against direct reads |
| Embedding model and contextualization | Optional; evaluate later |
| Hybrid fusion and reranking | Optional; evaluate only if simpler retrieval is insufficient |
| Candidate and final evidence limits | Set from evaluation, not guessed defaults |
| Latency and cost budgets | Set with the implemented retrieval path |
