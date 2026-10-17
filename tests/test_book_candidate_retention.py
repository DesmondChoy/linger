"""Candidate reduction must preserve answers and whole-request fallback coverage."""

from collections import Counter
from math import log

import pytest

from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem, LibrarianRequest
from apps.backend.hybrid_librarian import HybridLibrarian
from src.linger.agents.librarian.models import (
    BookRequestPart,
    BookRequestPlan,
    LibrarianBookRequestInput,
    book_request_span_errors,
)
from src.linger.contracts.session import ReaderStatement
from src.linger.contracts.reading import permits_scope
from src.linger.corpus.alice import BOOK as ALICE
from src.linger.corpus.douglass import BOOK as DOUGLASS
from src.linger.corpus.pinocchio import BOOK as PINOCCHIO
from src.linger.orchestration.book_evidence import (
    CONTEXT_CANDIDATES,
    EvidenceJudgementError,
    evidence_record_from_item,
    gather_book_candidates,
)


def scope_for(book, chapter_max):
    return BookScope(
        work_id=book.work_id, book_version_id=book.book_version_id, chapter_max=chapter_max,
    )


def answer_plan(text):
    return BookRequestPlan(parts=(BookRequestPart(
        context_spans=(), reader_spans=(text,), purpose="answer",
    ),))


def controlled_hybrid(monkeypatch, request, *, keyword_lines, semantic_lines, scores):
    """Use canonical windows and the production merge, with deterministic ranking inputs."""
    librarian = HybridLibrarian()
    windows = {
        candidate.source_lines: candidate
        for candidate in librarian._eligible_windows(request)
    }

    class Reranker:
        def rerank(self, query, documents):
            logits = {
                windows[lines].search_text: log(score / (1 - score))
                for lines, score in scores.items()
            }
            return [logits[document] for document in documents]

    librarian._reranker = Reranker()
    monkeypatch.setattr(librarian, "_bm25", lambda query, index: [windows[lines] for lines in keyword_lines])
    monkeypatch.setattr(
        librarian, "_semantic",
        lambda query, index, threshold: [windows[lines] for lines in semantic_lines],
    )
    return librarian


def test_pinocchio_overlap_preserves_the_unique_reaction_to_geppettos_sacrifice(monkeypatch):
    scope = scope_for(PINOCCHIO, 8)
    question = "How did Pinocchio respond when his father sold his coat to buy his A-B-C book?"
    request = LibrarianRequest(query=question, book_scopes=[scope])
    setup, reaction = (825, 883), (869, 886)
    librarian = controlled_hybrid(
        monkeypatch, request, keyword_lines=[setup, reaction], semantic_lines=[setup, reaction],
        scores={setup: 0.7, reaction: 0.9},
    )
    retrieved = librarian.retrieve_for_judgement(request).items
    assert [item.source_lines for item in retrieved] == [setup, reaction]
    assert "his tears" not in retrieved[0].excerpt
    assert "kissed him over and over" in retrieved[1].excerpt

    retained = gather_book_candidates(
        BookRequestPlan(parts=()), LibrarianBookRequestInput(current_line=question),
        book_scopes=(scope,), librarian=librarian,
    )

    assert any("his tears" in item.excerpt and "kissed him over and over" in item.excerpt for item in retained)
    assert all(item.chapter == 8 for item in retained)


def test_douglass_answer_survives_four_channel_interleave_without_losing_other_signals(monkeypatch):
    scope = scope_for(DOUGLASS, 11)
    question = "What happens when Douglass resists Covey?"
    request = LibrarianRequest(query=question, book_scopes=[scope])
    surname, background, surveillance, fight = (3350, 3369), (1945, 1975), (2045, 2072), (2196, 2344)
    librarian = controlled_hybrid(
        monkeypatch, request,
        keyword_lines=[surname, background, fight],
        semantic_lines=[surveillance, background, fight],
        scores={surname: 0.000021, background: 0.0773, surveillance: 0.1211, fight: 0.4982},
    )
    retrieved = librarian.retrieve_for_judgement(request).items
    assert [item.source_lines for item in retrieved] == [surname, background, surveillance, fight]
    assert max(retrieved, key=lambda item: item.relevance).source_lines == fight

    retained = gather_book_candidates(
        answer_plan(question), LibrarianBookRequestInput(current_line=question),
        book_scopes=(scope,), librarian=librarian,
    )

    retained_lines = {item.source_lines for item in retained}
    assert fight in retained_lines, "The strongest reranker answer was fourth in the hybrid interleave."
    assert {surname, surveillance} <= retained_lines, "Independent lexical and semantic recall must also survive."


class RoutingLibrarian:
    def __init__(self, query):
        self.query = query
        self.calls = []

    def retrieve_for_judgement(self, request):
        scope = request.book_scopes[0]
        self.calls.append((scope.work_id, request.query))
        if request.query.rstrip(".") != self.query.rstrip("."):
            return EvidenceBundle(items=[], retrieval_note="No match for the follow-up alone.")
        return EvidenceBundle(items=[
            EvidenceItem(
                evidence_id=f"{scope.work_id}-candidate-{rank}", work_id=scope.work_id,
                book_version_id=scope.book_version_id, chapter_id=f"{scope.book_version_id}-ch01",
                chapter=1, source_title="Book", location="Chapter 1", source_sha256="a" * 64,
                source_lines=(10 * rank + 1, 10 * rank + 5), excerpt=f"Passage {rank}",
                relevance=0.9 if scope.work_id == ALICE.work_id else 0.001,
            ) for rank in range(6)
        ], retrieval_note="One book dominates, but every book has fallback candidates.")


@pytest.mark.parametrize("in_prior_statement", [False, True])
def test_duplicate_planned_query_preserves_fallback_for_other_books(in_prior_statement):
    question = "Compare Alice and Pinocchio."
    original = LibrarianBookRequestInput(
        current_line="How do they compare?" if in_prior_statement else question,
        prior_reader_statements=(ReaderStatement(statement_id="prior", text=question),) if in_prior_statement else (),
    )
    scopes = (scope_for(ALICE, 5), scope_for(PINOCCHIO, 8))
    results = []
    for span in (question, question.rstrip(".")):
        plan = answer_plan(span)
        assert not book_request_span_errors(plan, original)
        librarian = RoutingLibrarian(question)
        retained = gather_book_candidates(plan, original, book_scopes=scopes, librarian=librarian)
        results.append({item.evidence_id for item in retained})

        assert sum(item.work_id == PINOCCHIO.work_id for item in retained) == CONTEXT_CANDIDATES
        assert all(count == 1 for count in Counter(librarian.calls).values()), "Reuse identical searches."
        assert (PINOCCHIO.work_id, question) in librarian.calls

    assert results[0] == results[1], "An exact-span punctuation choice cannot remove fallback evidence."


@pytest.mark.parametrize("unique_queries", [16, 17])
def test_query_budget_counts_distinct_searches_even_when_plan_repeats_context(unique_queries):
    question = "Compare Alice and Pinocchio."
    original = LibrarianBookRequestInput(
        current_line=question,
        prior_reader_statements=tuple(
            ReaderStatement(statement_id=f"prior-{index}", text=f"Explain book event {index}.")
            for index in range(1, unique_queries)
        ),
    )
    librarian = RoutingLibrarian(question)

    def gather():
        return gather_book_candidates(
            answer_plan(question), original, book_scopes=(scope_for(ALICE, 5),), librarian=librarian,
        )

    if unique_queries == 17:
        with pytest.raises(EvidenceJudgementError, match="retrieval query budget"):
            gather()
        assert librarian.calls == []
    else:
        gather()
        assert len(librarian.calls) == len(set(librarian.calls)) == 16


@pytest.mark.embeddings
@pytest.mark.parametrize(("book", "chapter_max", "question", "answer_quotes"), [
    pytest.param(
        PINOCCHIO, 36,
        "How did Pinocchio respond when he learned that his father had sold his coat to buy his A-B-C book?",
        ("unable to restrain his tears", "kissed him over and over"),
        id="pinocchio-gratitude",
    ),
    pytest.param(
        DOUGLASS, 11, "What happens when Douglass resists Covey?",
        ("I resolved to fight", "We were at it for nearly two hours", "he never laid the weight of his finger upon me in anger"),
        id="douglass-resistance",
    ),
    pytest.param(
        ALICE, 5, "How does Alice stop being trapped in the house?",
        ("she swallowed one of the cakes", "began shrinking directly", "she ran out of the house"),
        id="alice-house-escape",
    ),
])
def test_cached_models_retain_canonical_answers_within_the_reading_boundary(book, chapter_max, question, answer_quotes):
    from src.linger.orchestration.grounding import librarian_service

    scope = scope_for(book, chapter_max)
    retained = gather_book_candidates(
        answer_plan(question), LibrarianBookRequestInput(current_line=question),
        book_scopes=(scope,), librarian=librarian_service,
    )

    normalized_passages = [" ".join(item.excerpt.split()) for item in retained]
    for quote in answer_quotes:
        assert any(quote in passage for passage in normalized_passages), quote
    for item in retained:
        assert permits_scope(scope, item)
        assert librarian_service.fetch_by_id(item.evidence_id) == evidence_record_from_item(item)
