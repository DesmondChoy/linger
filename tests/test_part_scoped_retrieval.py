"""Each planned part keeps its own small candidate budget in the book it names."""

import pytest

from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from src.linger.agents.librarian.models import BookRequestPart, BookRequestPlan, LibrarianBookRequestInput
from src.linger.orchestration.book_evidence import (
    CONTEXT_CANDIDATES, PART_CANDIDATES, gather_book_candidates,
)

ALICE = BookScope(work_id="pg11", book_version_id="pg11-v1", chapter_max=5)
KELLER = BookScope(work_id="pg2397", book_version_id="pg2397-v1", chapter_max=22)
NAMED = "Alice telling the Caterpillar she has changed"
THEME = "a bundle of perceptions"
LINE = f"{NAMED}, and {THEME}."


def part(text):
    return BookRequestPart(context_spans=(), purpose="reference", reader_spans=(text,))


OFFSETS = {"named": 0, "theme": 1000, "line": 2000}


def window(scope, label, rank, relevance, lines=None):
    start = lines[0] if lines else OFFSETS[label] + 10 * rank
    end = lines[1] if lines else start + 5
    return EvidenceItem(
        evidence_id=f"{scope.work_id}-{label}-{rank}", work_id=scope.work_id,
        book_version_id=scope.book_version_id, chapter_id=f"{scope.work_id}-ch01", chapter=1,
        source_title="Book", location="Chapter 1", source_sha256="a" * 64,
        source_lines=(start, end), excerpt=f"{label} {rank}", relevance=relevance,
    )


class Librarian:
    """The named part dominates only in Alice; the theme and the Line match weakly everywhere."""

    def __init__(self):
        self.calls = []

    def retrieve_for_judgement(self, request):
        scope = request.book_scopes[0]
        self.calls.append((scope.work_id, request.query))
        if request.query == NAMED:
            relevance = 0.99 if scope.work_id == "pg11" else 0.001
            label = "named"
        elif request.query == THEME:
            relevance, label = 0.02, "theme"
        else:
            relevance, label = 0.01, "line"
        return EvidenceBundle(
            items=[window(scope, label, rank, relevance) for rank in range(8)],
            retrieval_note="controlled",
        )


def gather(plan, librarian):
    return gather_book_candidates(
        plan, LibrarianBookRequestInput(current_line=LINE),
        book_scopes=(ALICE, KELLER), librarian=librarian,
    )


def labels_by_book(items):
    counts = {}
    for item in items:
        key = (item.work_id, item.excerpt.split()[0])
        counts[key] = counts.get(key, 0) + 1
    return counts


def test_a_dominant_named_part_stays_in_its_book_and_a_theme_searches_every_book():
    librarian = Librarian()
    items = gather(BookRequestPlan(parts=(part(NAMED), part(THEME))), librarian)

    # Both parts are searched everywhere; routing decides only what is kept.
    assert {call for call in librarian.calls if call[1] != LINE} == {
        ("pg11", NAMED), ("pg2397", NAMED), ("pg11", THEME), ("pg2397", THEME),
    }
    assert labels_by_book(items) == {
        ("pg11", "named"): PART_CANDIDATES,
        ("pg11", "theme"): PART_CANDIDATES, ("pg2397", "theme"): PART_CANDIDATES,
        ("pg11", "line"): CONTEXT_CANDIDATES, ("pg2397", "line"): CONTEXT_CANDIDATES,
    }


def test_without_a_plan_the_whole_request_keeps_the_full_budget():
    items = gather(BookRequestPlan(parts=()), Librarian())
    assert labels_by_book(items) == {("pg11", "line"): 8, ("pg2397", "line"): 8}


@pytest.mark.parametrize(("second", "kept"), [
    ((1003, 1010), True), ((1005, 1020), True),
    ((1003, 1009), False), ((1000, 1009), False),
])
def test_only_a_fully_contained_window_is_dropped(second, kept):
    class Overlapping:
        def retrieve_for_judgement(self, request):
            return EvidenceBundle(items=[
                window(ALICE, "first", 0, 0.9, lines=(1000, 1009)),
                window(ALICE, "second", 1, 0.8, lines=second),
            ], retrieval_note="overlap")

    items = gather_book_candidates(
        BookRequestPlan(parts=()), LibrarianBookRequestInput(current_line=LINE),
        book_scopes=(ALICE,), librarian=Overlapping(),
    )
    assert ("pg11-second-1" in {item.evidence_id for item in items}) is kept


@pytest.mark.embeddings
def test_captured_combined_scenario_plans_keep_every_required_passage():
    from evals.librarian.part_recall import run

    results = run()
    assert sum(result.found for result in results) == sum(result.required for result in results) > 0
    # These frozen plans have at most four named queries and one whole-Line
    # fallback across five books. Broadcasting named queries would exceed this.
    named_pool_budget = 4 * PART_CANDIDATES + 5 * CONTEXT_CANDIDATES
    assert max(result.pool_size for result in results if result.case_id.startswith("scene-07")) <= named_pool_budget


def test_an_experiment_can_opt_into_more_windows_per_part():
    items = gather_book_candidates(
        BookRequestPlan(parts=(part(NAMED), part(THEME))), LibrarianBookRequestInput(current_line=LINE),
        book_scopes=(ALICE, KELLER), librarian=Librarian(), part_candidates=5,
    )
    assert labels_by_book(items) == {
        ("pg11", "named"): 5, ("pg11", "theme"): 5, ("pg2397", "theme"): 5,
        ("pg11", "line"): CONTEXT_CANDIDATES, ("pg2397", "line"): CONTEXT_CANDIDATES,
    }
