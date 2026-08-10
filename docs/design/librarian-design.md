# Librarian Subsystem Design

Status: **Draft implementation design**

This document defines the Librarian subsystem from book ingestion through the evidence bundle returned to Muse. It elaborates on the Librarian responsibilities and safeguards in [`../specification.md`](../specification.md).

## 1. Purpose and scope

The Librarian subsystem prepares books for retrieval and returns relevant, traceable, spoiler-safe evidence to Muse. It has two flows:

1. **Offline book preprocessing** converts a source book into validated, chapter-aware chunks and searchable indexes.
2. **Online retrieval** searches only the chunks permitted for the current request, ranks the results, judges whether they can answer Muse's request, and returns a typed evidence bundle.

The offline flow is deterministic application code, not an LLM agent. The online flow contains the Librarian reasoning agent and deterministic retrieval tools. Librarian never writes a user-facing response, changes access restrictions, or authorises output release.

### 1.1 Responsibilities

Librarian may:

- understand Muse's evidence request;
- choose from permitted retrieval strategies;
- call keyword, semantic, fusion, and reranking tools;
- judge whether the returned evidence is sufficient, weak, or absent; and
- return exact source chunks and their metadata to Muse.

Librarian may not:

- widen a spoiler or account boundary;
- retrieve an unpublished book version;
- invent, rewrite, or silently truncate source evidence;
- save, modify, or delete memories;
- draft the final user-facing response; or
- bypass Provenance or deterministic validation.

## 2. System overview

### 2.1 The two flows

```text
OFFLINE BOOK-PREPROCESSING FLOW

Book source
    ↓
Download and verify
    ↓
Clean and normalize
    ↓
Detect and validate chapters
    ↓
Split chapters into chunks
    ↓
Assign evidence IDs
    ↓
Build keyword and semantic indexes
    ↓
Publish searchable book version


ONLINE RETRIEVAL FLOW

Muse request + trusted policy context
    ↓
Validate request and spoiler boundary
    ↓
Create permitted search area
    ↓
Keyword search + semantic search
    ↓
Filter, combine, and deduplicate
    ↓
Rerank
    ↓
Decide evidence strength
    ↓
Return evidence bundle to Muse
```

The offline output is the online flow's searchable input:

```text
Published book metadata
Chapter metadata
Chunk records
Keyword index
Semantic index
    ↓
Online retrieval
```

The online flow must never search a book version that has not completed preprocessing successfully.

### 2.2 Component ownership

| Component | Flow | Responsibility |
|---|---|---|
| Book processor | Offline | Downloads, verifies, cleans, and structures books |
| Chunker | Offline | Creates chapter-safe chunks and evidence IDs |
| Index builder | Offline | Builds keyword and semantic indexes |
| Policy service | Online | Supplies trusted account and spoiler restrictions |
| Librarian agent | Online | Plans retrieval and judges evidence strength |
| Retrieval service | Online | Searches only permitted chunks |
| Reranker | Online | Orders candidate chunks by relevance to the request |
| Muse | Consumer | Uses the evidence bundle to draft a candidate response |
| Provenance | Downstream | Checks Muse's complete response against the evidence |
| Citation validator | Downstream | Resolves evidence IDs and validates exact quotations |

The Librarian agent may choose how to search, but it cannot widen what the retrieval service permits it to search.

## 3. Offline book-preprocessing flow

### 3.1 Purpose

The offline flow converts an unstructured source book into stable, chapter-aware chunks that can be safely searched and cited. It runs when a new book or a new revision of an existing book is appended to the corpus.

The corpus is append-only:

- an existing book version is never replaced or modified;
- a new revision creates a separate book version;
- old and new revisions may coexist; and
- existing evidence IDs remain resolvable.

### 3.2 Flow overview

```text
Preprocessing request
      ↓
Retrieve source book and metadata
      ↓
Verify eligibility and source hashes
      ↓
Clean and normalize text
      ↓
Detect and validate chapters
      ↓
Create chapter-safe chunks
      ↓
Assign evidence IDs
      ↓
Build keyword and semantic indexes
      ↓
Validate all stored records
      ↓
Publish book version
```

### 3.3 Input contract

The preprocessing input identifies an authoritative source. Metadata such as the title, author, language, and copyright status is retrieved and verified rather than trusted from user-entered values.

```python
class BookPreprocessingRequest(BaseModel):
    source_type: Literal["project_gutenberg"]
    gutenberg_id: int
    source_url: HttpUrl
```

Example:

```json
{
  "source_type": "project_gutenberg",
  "gutenberg_id": 11,
  "source_url": "https://www.gutenberg.org/cache/epub/11/pg11.txt"
}
```

The first implementation uses [Project Gutenberg eBook #11, *Alice's Adventures in Wonderland*](https://www.gutenberg.org/ebooks/11).

### 3.4 Source acquisition and verification

The book processor:

1. downloads the plain-text source;
2. records the requested and resolved URLs;
3. records the download time;
4. calculates a SHA-256 hash of the raw file;
5. retrieves the official Gutenberg metadata; and
6. verifies that the book is exclusively English, public domain, and available as plain text.

Example source metadata:

```json
{
  "gutenberg_id": 11,
  "requested_url": "https://www.gutenberg.org/ebooks/11.txt.utf-8",
  "resolved_url": "https://www.gutenberg.org/cache/epub/11/pg11.txt",
  "downloaded_at_utc": "2026-08-10T10:00:00Z",
  "raw_sha256": "abc123..."
}
```

### 3.5 Text cleaning and normalization

The processor removes material outside the book body, including the Project Gutenberg header, footer, download notices, and licence text. It then normalizes line endings, Unicode representation, repeated whitespace, and paragraph separators.

Normalization must preserve:

- original spelling and punctuation;
- paragraph boundaries;
- chapter headings;
- dialogue; and
- poem formatting where practical.

The normalized text is the authoritative source for section boundaries, chunks, searches, evidence resolution, and quotation validation. The processor records its SHA-256 hash.

### 3.6 Section detection

`Section` is the general internal term because books may use chapters, parts, books, letters, acts, scenes, or stories.

Example:

```json
{
  "section_id": "pg11-v7be31a2f-ch001",
  "section_type": "chapter",
  "section_number": 1,
  "section_title": "Down the Rabbit-Hole",
  "start_character": 0,
  "end_character": 11240
}
```

Section detection must distinguish real headings in the body from repeated headings in a table of contents.

### 3.7 Section validation

Before chunking, deterministic checks verify that:

- sections are in source order;
- sections do not overlap;
- every section contains body text;
- all searchable body text belongs to a section;
- table-of-contents entries were not treated as body sections; and
- the detected section count agrees with the contents list when one exists.

Failure prevents publication:

```json
{
  "status": "review_required",
  "reason": "Detected 24 chapter headings, but the contents list contains 12."
}
```

A human may correct the section boundaries and rerun preprocessing. The pipeline does not guess past a failed structural validation.

### 3.8 Chunk creation

Initial settings:

```yaml
chunk_size_tokens: 450
chunk_overlap_tokens: 75
```

Rules:

- one chunk belongs to exactly one book version;
- one chunk belongs to exactly one section;
- a chunk never crosses a section boundary;
- paragraph boundaries are preferred when choosing a split point;
- overlap occurs only between neighbouring chunks in the same section;
- every chunk records its exact character range in the normalized text; and
- a very short final chunk may be combined with its preceding chunk.

Example:

```text
Chapter 1
├── Chunk 1: tokens 1–450
├── Chunk 2: tokens 376–825
├── Chunk 3: tokens 751–1200
└── Chunk 4: remaining chapter text
```

### 3.9 Evidence identity

The evidence ID identifies a chunk from an exact book revision:

```text
pg11-v7be31a2f-ch001-ck003
```

Its components are:

```text
pg11       Project Gutenberg work ID
v7be31a2f  Prefix of the normalized book-text hash
ch001      Chapter or section number
ck003      Chunk number within the section
```

The full hash remains in the stored record and is used to verify the shortened version component. A collision during ingestion is a hard failure; the system does not silently lengthen or replace an existing ID.

Example chunk record:

```json
{
  "evidence_id": "pg11-v7be31a2f-ch001-ck003",
  "work_id": "pg11",
  "book_version_id": "pg11-v7be31a2f",
  "book_title": "Alice's Adventures in Wonderland",
  "author": "Lewis Carroll",
  "section_type": "chapter",
  "section_number": 1,
  "section_title": "Down the Rabbit-Hole",
  "chunk_number": 3,
  "start_character": 8240,
  "end_character": 9468,
  "text_hash": "3f924...",
  "text": "Exact normalized source text..."
}
```

Because the book-version hash is part of the ID, two revisions of Gutenberg work #11 remain distinct:

```text
pg11-v7be31a2f-ch001-ck003
pg11-v91c44d08-ch001-ck003
```

Appending another book does not change existing evidence IDs.

### 3.10 Keyword-index construction

Every validated chunk is added to the keyword index. The entry keeps the evidence ID, book version, section position, and exact normalized text as filterable or resolvable metadata.

```json
{
  "evidence_id": "pg11-v7be31a2f-ch001-ck003",
  "book_version_id": "pg11-v7be31a2f",
  "section_number": 1,
  "text": "Exact normalized source text..."
}
```

Failed and unpublished book versions are not indexed for online retrieval.

### 3.11 Semantic-index construction

Every validated chunk is converted into an embedding and stored with its evidence ID and filterable book and section metadata.

```json
{
  "evidence_id": "pg11-v7be31a2f-ch001-ck003",
  "embedding_model": "TBD",
  "embedding_version": "TBD",
  "embedding": ["numeric vector omitted"]
}
```

The embedding model and version are recorded. Changing the embedding model creates a new derived index; it does not mutate the underlying book version or evidence records.

### 3.12 Publication

A book version becomes searchable only when:

- source eligibility and hashes are valid;
- section validation passes;
- chunk ranges and hashes are valid;
- every evidence ID is unique and resolves to the expected text;
- keyword indexing succeeds; and
- semantic indexing succeeds.

Partial output remains unpublished and cannot be selected by the online flow.

### 3.13 Output contract

```python
class PublishedBookVersion(BaseModel):
    status: Literal["published"]
    work_id: str
    book_version_id: str
    title: str
    author: str
    section_count: int
    chunk_count: int
    raw_sha256: str
    normalized_text_sha256: str
    keyword_index_status: Literal["ready"]
    semantic_index_status: Literal["ready"]
    warnings: list[str]


class PreprocessingFailure(BaseModel):
    status: Literal["review_required", "failed"]
    reason: str
```

Successful example; counts are illustrative until preprocessing runs:

```json
{
  "status": "published",
  "work_id": "pg11",
  "book_version_id": "pg11-v7be31a2f",
  "title": "Alice's Adventures in Wonderland",
  "author": "Lewis Carroll",
  "section_count": 12,
  "chunk_count": 84,
  "raw_sha256": "abc123...",
  "normalized_text_sha256": "7be31a2f...",
  "keyword_index_status": "ready",
  "semantic_index_status": "ready",
  "warnings": []
}
```

### 3.14 Offline-flow verification

Tests cover:

- Gutenberg header and footer removal;
- section detection and order;
- table-of-contents headings not being treated as body sections;
- no chunk crossing a section boundary;
- correct overlap and character ranges;
- unique and reproducible evidence IDs;
- every evidence ID resolving to exact normalized source text;
- a new revision producing a new book-version ID;
- append-only behavior; and
- any failed validation preventing publication.

## 4. Online retrieval flow

### 4.1 Purpose

The online flow receives an evidence request from Muse, searches only the book chunks permitted by trusted application state, and returns a typed evidence bundle. The Librarian agent plans the search and judges answerability; deterministic services enforce scope and execute retrieval.

### 4.2 Flow overview

```text
Muse retrieval request
      +
Trusted application context
      ↓
Validate request
      ↓
Resolve spoiler boundary
      ↓
Create permitted search area
      ↓
Keyword and semantic search
      ↓
Apply method-specific thresholds
      ↓
Combine rankings and deduplicate
      ↓
Rerank candidates
      ↓
Decide evidence strength
      ↓
Build evidence bundle
      ↓
Return to Muse
```

### 4.3 Input contract

Muse supplies the evidence request:

```python
class LibrarianRequest(BaseModel):
    query: str
    book_version_ids: list[str]
    maximum_results: int = 5
    reason: str
```

```json
{
  "query": "Why does Alice follow the White Rabbit?",
  "book_version_ids": ["pg11-v7be31a2f"],
  "maximum_results": 5,
  "reason": "Muse needs textual support for a reflection."
}
```

Trusted application code separately supplies the policy context:

```python
class ReadingBoundary(BaseModel):
    section_number: int
    status: Literal["started", "completed"]


class RetrievalContext(BaseModel):
    account_id: str
    spoiler_boundaries: dict[str, ReadingBoundary]
```

```json
{
  "account_id": "account-123",
  "spoiler_boundaries": {
    "pg11-v7be31a2f": {
      "section_number": 5,
      "status": "completed"
    }
  }
}
```

Muse cannot provide, modify, or override `account_id` or the spoiler boundaries.

### 4.4 Request validation

Before retrieval, application code checks that:

- the query is non-empty;
- every requested book version exists and is published;
- the requested result count is between one and the configured maximum;
- a spoiler boundary exists for every requested book;
- the stated section exists in that book version; and
- the current section is explicitly marked `started` or `completed`.

Possible validation outcomes are `valid`, `clarification_needed`, and `invalid`.

If the user says only that they are "on Chapter 5," retrieval does not run:

```json
{
  "status": "clarification_needed",
  "question": "Have you started or completed Chapter 5?"
}
```

### 4.5 Spoiler-boundary resolution

The boundary resolves as follows:

```text
Started Chapter 5:   permit Chapters 1–4
Completed Chapter 5: permit Chapters 1–5
```

Each requested book version receives its own boundary. A missing, invalid, or ambiguous boundary fails closed; it never defaults to the whole book.

### 4.6 Permitted search-area construction

The retrieval service constructs an allowed set or filtered index query from:

```text
Requested published book versions
AND
Section position within each spoiler boundary
```

The search backend must apply this restriction as part of its query or through a pre-partitioned allowed collection. Searching the full book and removing forbidden results afterward is not permitted.

Forbidden chunk text is never returned to the Librarian agent, Muse, the reranker, or downstream model context.

When private-memory retrieval is added, the allowed set will also require the authenticated account, active status, and non-deleted status before search.

### 4.7 Keyword retrieval

Keyword retrieval is suited to names, places, exact phrases, known quotations, objects, and explicit events.

Input:

```json
{
  "query": "Why does Alice follow the White Rabbit?",
  "allowed_book_versions": ["pg11-v7be31a2f"],
  "maximum_sections": {
    "pg11-v7be31a2f": 5
  },
  "limit": 10
}
```

Output:

```json
{
  "results": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "rank": 1,
      "raw_score": 7.42
    }
  ]
}
```

Initial setting:

```yaml
keyword_candidates: 10
```

Raw keyword scores such as BM25 are not assumed to use a zero-to-one scale, so the shared `0.5` threshold does not apply to them.

### 4.8 Semantic retrieval

Semantic retrieval is suited to themes, emotions, paraphrases, and similar meanings expressed with different words.

Input:

```json
{
  "query": "Why does Alice follow the White Rabbit?",
  "allowed_book_versions": ["pg11-v7be31a2f"],
  "maximum_sections": {
    "pg11-v7be31a2f": 5
  },
  "limit": 10,
  "minimum_score": 0.5
}
```

Output:

```json
{
  "results": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "rank": 1,
      "score": 0.83
    }
  ]
}
```

Initial settings:

```yaml
semantic_candidates: 10
semantic_score_threshold: 0.5
```

The threshold is configurable and applies only when the chosen similarity measure has the documented zero-to-one interpretation.

### 4.9 Ranking fusion and duplicate handling

Ranking fusion combines the keyword and semantic result lists without directly comparing their incompatible raw scores. The exact fusion method is TBD.

Input:

```json
{
  "keyword_results": ["keyword result records"],
  "semantic_results": ["semantic result records"]
}
```

The same evidence ID may appear in both lists. It is merged into one candidate that records both retrieval paths:

```json
{
  "evidence_id": "pg11-v7be31a2f-ch001-ck002",
  "retrieval_methods": ["keyword", "semantic"],
  "keyword_rank": 2,
  "semantic_rank": 1,
  "fusion_score": 0.0325
}
```

Initial limits:

```yaml
maximum_combined_candidates: 20
maximum_rerank_candidates: 15
```

### 4.10 Reranking

Reranking answers: **Which candidate chunks are most relevant to this exact request?**

At the product level, Librarian owns reranking. Technically, the Librarian agent calls a separate reranking tool. The tool orders individual chunks; it does not assign the bundle-level labels `sufficient`, `weak`, or `none`.

Only permitted chunks may be sent to the reranker.

Input:

```json
{
  "query": "Why does Alice follow the White Rabbit?",
  "candidates": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "text": "Exact chunk text..."
    }
  ],
  "limit": 15
}
```

Output:

```json
{
  "results": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "rank": 1,
      "score": 0.91
    }
  ]
}
```

Initial setting:

```yaml
reranker_score_threshold: 0.5
```

The threshold applies only if the selected reranker returns a documented normalized zero-to-one score. The reranking model is TBD.

### 4.11 Evidence-strength decision

Evidence strength answers a different question: **Can the best retrieved passages answer Muse's request?**

After reranking, the Librarian agent inspects the top permitted evidence and returns one bundle-level label:

- `sufficient`: the evidence directly supports an answer;
- `weak`: the evidence provides relevant context but does not fully support an answer; or
- `none`: no useful evidence was found within the permitted sources.

Input:

```json
{
  "query": "Does Alice regret following the White Rabbit?",
  "top_evidence": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "text": "Exact chunk text..."
    }
  ]
}
```

Output:

```json
{
  "evidence_strength": "weak",
  "strength_reason": "The passage shows Alice following the Rabbit but does not show that she regrets doing so."
}
```

A high retrieval or reranker score does not automatically mean sufficient evidence. Weak evidence remains in the bundle so Muse can understand the available context and its limitation. `none` normally has an empty evidence list.

The strength label is an advisory reasoning result, not release authority. Provenance independently reviews Muse's eventual use of the evidence.

### 4.12 Evidence-bundle construction

The final bundle contains no more than five useful chunks. It may contain fewer; Librarian does not add irrelevant chunks to meet the limit.

Every returned item contains:

- evidence ID;
- exact chunk text;
- work and book-version IDs;
- book title and author;
- section type, number, and title;
- retrieval methods;
- final rank; and
- reranker score when available.

It never contains forbidden text, later-chapter summaries, generated quotations, or unsupported conclusions.

### 4.13 Output contract

The result is a typed union:

```python
LibrarianResult = Annotated[
    EvidenceFound | ClarificationNeeded | NoEvidence | RetrievalFailed,
    Field(discriminator="status"),
]
```

#### Sufficient evidence

```json
{
  "status": "evidence_found",
  "query": "Why does Alice follow the White Rabbit?",
  "evidence_strength": "sufficient",
  "strength_reason": "The passage directly describes Alice following the Rabbit out of curiosity.",
  "evidence": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck002",
      "text": "Exact source text...",
      "source": {
        "work_id": "pg11",
        "book_version_id": "pg11-v7be31a2f",
        "book_title": "Alice's Adventures in Wonderland",
        "author": "Lewis Carroll",
        "section_type": "chapter",
        "section_number": 1,
        "section_title": "Down the Rabbit-Hole"
      },
      "retrieval_methods": ["keyword", "semantic"],
      "rank": 1,
      "reranker_score": 0.91
    }
  ],
  "limitations": [],
  "warnings": []
}
```

#### Weak evidence

```json
{
  "status": "evidence_found",
  "query": "Does Alice regret following the White Rabbit?",
  "evidence_strength": "weak",
  "strength_reason": "The passages describe the consequences but do not directly express regret.",
  "evidence": [
    {
      "evidence_id": "pg11-v7be31a2f-ch001-ck004",
      "text": "Exact related source text...",
      "source": {
        "work_id": "pg11",
        "book_version_id": "pg11-v7be31a2f",
        "book_title": "Alice's Adventures in Wonderland",
        "author": "Lewis Carroll",
        "section_type": "chapter",
        "section_number": 1,
        "section_title": "Down the Rabbit-Hole"
      },
      "retrieval_methods": ["semantic"],
      "rank": 1,
      "reranker_score": 0.67
    }
  ],
  "limitations": [
    "No passage directly states that Alice regrets her decision."
  ],
  "warnings": []
}
```

#### No evidence

```json
{
  "status": "no_evidence",
  "query": "Does Alice regret following the White Rabbit?",
  "evidence_strength": "none",
  "strength_reason": "No relevant passage was found within the permitted chapters.",
  "evidence": [],
  "limitations": [
    "Only Chapters 1–5 were searchable."
  ],
  "warnings": []
}
```

#### Clarification required

```json
{
  "status": "clarification_needed",
  "question": "Have you started or completed Chapter 5?",
  "evidence": []
}
```

#### Retrieval failure

```json
{
  "status": "retrieval_failed",
  "reason": "The permitted reading boundary could not be verified.",
  "evidence": []
}
```

### 4.14 Failure and degraded operation

The online flow fails closed on policy and evidence integrity but may degrade safely when an optional retrieval method fails:

- if the spoiler boundary cannot be verified, return `retrieval_failed` and do not search;
- if semantic search fails, keyword search may continue and the result records `keyword_only` mode;
- if reranking fails, fusion-ranked results may be returned with a warning;
- if an evidence ID does not resolve, exclude it and fail the request if the remaining bundle cannot support its declared strength; and
- no fallback may expand the permitted book versions, chapters, accounts, or result limit.

Example degraded metadata:

```json
{
  "retrieval_mode": "keyword_only",
  "warnings": ["Semantic search was unavailable."]
}
```

### 4.15 Online-flow verification

Tests cover:

- exact quotation, named entity, paraphrase, and theme queries;
- expected evidence appearing in the top five;
- keyword and semantic duplicates being merged;
- `started` and `completed` boundaries;
- ambiguous boundaries requiring clarification before search;
- later chapters never reaching search results, reranking, or model context;
- weak evidence including the relevant chunks and limitation;
- absent evidence producing an empty evidence list;
- every returned evidence ID resolving to exact source text;
- multiple book revisions remaining distinguishable;
- semantic-search and reranker failures degrading as specified; and
- no failure path widening the allowed search area.

## 5. Downstream integration

The Librarian result is evidence for Muse, not permission to display a response:

```text
Librarian evidence bundle
      ↓
Muse drafts typed candidate response
      ↓
Provenance reviews complete response and cited evidence
      ↓
Application validates evidence IDs, exact quotations,
source locations, account scope, and spoiler boundaries
      ↓
Release or application-authored safe decline
```

Muse should use `evidence_strength` to calibrate its response:

- `sufficient`: answer using the cited evidence;
- `weak`: distinguish the available context from any tentative interpretation; and
- `none`: state that no support was found within the permitted material.

Provenance independently determines whether Muse followed those rules.

## 6. Initial configuration

```yaml
librarian:
  preprocessing:
    chunk_size_tokens: 450
    chunk_overlap_tokens: 75
    corpus_mode: append_only

  retrieval:
    keyword_candidates: 10
    semantic_candidates: 10
    semantic_score_threshold: 0.5
    maximum_combined_candidates: 20
    maximum_rerank_candidates: 15
    reranker_score_threshold: 0.5
    final_evidence_limit: 5
```

All thresholds and limits are overridable configuration. They are initial values, not validated quality claims, and must be revisited through evaluation.

## 7. Implementation sequence

### 7.1 Offline vertical slice

1. Process Gutenberg #11.
2. Validate its 12 chapters.
3. Produce 450-token chunks with 75-token overlap.
4. Assign evidence IDs and verify their source ranges.
5. Build keyword and semantic indexes.
6. Publish the book version only after all validation passes.

### 7.2 Online vertical slice

1. Accept the typed Muse request and trusted context separately.
2. Validate and resolve the spoiler boundary.
3. Construct the permitted search area.
4. Run keyword and semantic retrieval.
5. Fuse and deduplicate candidates.
6. Rerank no more than 15 chunks.
7. Decide evidence strength.
8. Return no more than five useful evidence records.

### 7.3 End-to-end integration

1. Pass the evidence bundle to Muse.
2. Pass Muse's candidate and cited evidence to Provenance.
3. Validate evidence IDs and exact quotations after semantic approval.
4. Exercise spoiler suppression and safe-decline paths end to end.

## 8. Open decisions

| Decision | Status |
|---|---|
| First book | Gutenberg #11 |
| Corpus lifecycle | Append-only |
| Ambiguous current chapter | Ask whether started or completed |
| Chunk size | 450 tokens |
| Chunk overlap | 75 tokens |
| Keyword candidates | 10 |
| Semantic candidates | 10 |
| Semantic threshold | 0.5, configurable |
| Combined candidates | Up to 20 |
| Rerank candidates | Up to 15 |
| Reranker threshold | 0.5 when score is normalized, configurable |
| Final evidence | Up to 5 useful chunks |
| Evidence strength | Whether the evidence can answer the request |
| Embedding model | TBD |
| Reranking model | TBD |
| Ranking-fusion method | TBD |
| Evidence-strength implementation | TBD |
| Latency limit | TBD; prefer cheap and fast |
| Cost limit | TBD; prefer cheap and fast |
