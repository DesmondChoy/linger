# How book retrieval works today

This describes, for Sculptor's error analysis and research, how Linger finds
book passages for a reader's question, using *The Adventures of Pinocchio* as
the example. It reflects the current best state: Experiment 3's Stage 2
chapter tags with tag-reading search.

## 1. The book

- 36 chapters, about 39,000 words; chapters run from about 400 to 2,900 words.
- Each chapter has reviewed tags: a one-sentence `routing_description`, a list
  of `characters`, and a few `retrieval_cues`.
- The book text never changes. Passages handed on are exact book text with
  their chapter and line numbers; replies may quote or paraphrase them.

## 2. Windows

Each chapter is cut into overlapping **windows** of about 350 words, built
from whole paragraphs, overlapping by about 60 words and never crossing a
chapter. *Pinocchio* has 166 windows. A window is the unit search ranks, the
Librarian reads, and Muse quotes. Its ID names its chapter and line range,
for example `pg500-v6bdc1734-ch22-ln2551-2605`.

For search only, each window's text is followed by its chapter's tags. The
reader never sees the tags. The traces list every chapter's current tags.

## 3. Planning

Before search, the Librarian's planning model splits the reader's question
into parts, copying exact reader wording. In this experiment the plans are
fixed. For most practice questions the single part is the question itself.

## 4. Search, once per query

The queries are each planned part plus the whole question, with duplicates
removed. The book's author name is dropped from a query. Search covers only
chapters the reader has reached (here, all 36). For each query:

1. **Keyword search (BM25)** ranks windows by shared words; the top 10 with a
   score above zero are kept.
2. **Meaning-based search** compares an embedding of the query
   (`BAAI/bge-small-en-v1.5`) with each window's; the top 10 are kept. The
   embedding reads at most 512 tokens of a window's search text, so the end
   of a long window, or its appended tags, can be cut off.
3. **Fusion.** Reciprocal-rank fusion merges the two lists, drops windows that
   mostly overlap a better one, and keeps at most 15.
4. **Reranking.** A small cross-encoder (`ms-marco-MiniLM-L-6-v2`) reads the
   query beside each unique candidate from steps 1 and 2 (up to 20) and scores
   it from 0 to 1. A pair longer than its 512-token limit is scored in pieces,
   keeping the best piece's score.
5. **Taking turns.** The query's candidate list takes one window from each
   list in turn: the best keyword hit, the best fused hit, the best meaning
   hit, the best reranked hit, then the second of each, and so on, skipping
   repeats.

## 5. The pool handed to the Librarian

- From each **planned part's** query, the **first 3** windows of that list
  are kept. These are usually the top keyword hit, the top fused hit, and the
  top meaning hit; the reranker's choice enters only when those repeat.
- From the **whole-question** query, when it differs from every part, the
  first 2 are kept. When the plan is empty, it keeps up to 20.
- The kept lists from all queries are merged by taking turns again.
- A window is then dropped when at least half of its own lines are covered by
  an earlier window from the same chapter, and at most 20 are kept per book.

The result is the **pool**: usually 2 to 6 windows, about 1,300 words.

## 6. Selection

The Librarian's assessment model reads the plan, the original question, and
the pool, and selects **at most 5 windows** that answer it, with a judgement of
`sufficient`, `weak`, or `none`, a reason, and limitations. The selected
windows are what Muse may draw on. If its answer fails validation twice, the
need gets no selection; the traces show that as an error.

## 7. What the traces show

A practice need passes when a selected window contains its answer quote. At
the current best state 17 of 20 pass. For every practice need the traces show
the plan, the queries, each query's keyword, meaning, fused, and turn-taking
lists with scores, the pool, and the Librarian's selection, judgement, reason,
and any error (reasons were not captured for this baseline). For each miss
they add the answering window and its keyword and meaning ranks among all 166
windows, as a range when other windows tie.

## 8. Fixed limits

Any proposed change must keep:

- quoted passages exact, with chapter and line numbers;
- the Librarian's final selection made from today's windows (about 350 words
  each), so every approach is scored on the same unit; an approach may change
  how windows are found, ranked, or read, and how much text the Librarian
  reads, which is reported as cost;
- the reading boundary: no window from a chapter the reader has not reached;
- the book text, test questions, answer quotes, frozen plans, and scoring
  unchanged;
- a build of a few days at most.

Sculptor may write data (for example tags at chapter or window level), and it
may specify changes to how search, the pool, or the Librarian's reading work.
