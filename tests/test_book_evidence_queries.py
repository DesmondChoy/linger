"""A planned part that names an author searches that book, without the name."""

from apps.backend.contracts import BookScope
from src.linger.agents.librarian.models import (
    BookRequestPlan,
    BookRequestPart,
    LibrarianBookRequestInput,
)
from src.linger.orchestration.book_evidence import _search_requests

KELLER = BookScope(work_id="pg2397", book_version_id="pg2397-vb3cc1e13", chapter_max=22)
ALICE = BookScope(work_id="pg11", book_version_id="pg11-v01b38ea4", chapter_max=5)
PINOCCHIO = BookScope(work_id="pg500", book_version_id="pg500-v6bdc1734", chapter_max=30)
LIBRARY = (ALICE, PINOCCHIO, KELLER)
LINE = "Keller forgetting all about college at the lake. What does that say about me?"


def _plan(*spans: str) -> BookRequestPlan:
    return BookRequestPlan(parts=tuple(
        BookRequestPart(reader_spans=(span,), context_spans=(), purpose="reference", uncertain=False)
        for span in spans
    ))


def test_a_part_naming_an_author_searches_only_that_book_without_the_name():
    searches = _search_requests(
        _plan("Keller forgetting all about college at the lake"),
        LibrarianBookRequestInput(current_line=LINE),
        LIBRARY,
    )
    assert searches[0] == ("forgetting all about college at the lake", (KELLER,))


def test_the_readers_own_words_are_searched_intact_across_every_book():
    searches = _search_requests(
        _plan("Keller forgetting all about college at the lake"),
        LibrarianBookRequestInput(current_line=LINE),
        LIBRARY,
    )
    assert (LINE, LIBRARY) in searches


def test_a_part_naming_no_author_searches_every_granted_book():
    searches = _search_requests(
        _plan("Alice telling the Caterpillar she's changed several times"),
        LibrarianBookRequestInput(current_line="A question"),
        LIBRARY,
    )
    assert searches[0] == ("Alice telling the Caterpillar she's changed several times", LIBRARY)


def test_full_name_and_possessive_are_removed_but_the_first_name_stays():
    searches = _search_requests(
        _plan("Helen Keller at the lake", "Keller's teacher spelling water", "Helen at the pump"),
        LibrarianBookRequestInput(current_line="Which moments matter?"),
        (KELLER,),
    )
    assert [text for text, _ in searches[:3]] == ["at the lake", "teacher spelling water", "Helen at the pump"]


def test_names_of_books_not_granted_are_left_alone():
    searches = _search_requests(
        _plan("Keller forgetting college at the lake"),
        LibrarianBookRequestInput(current_line="A question"),
        (ALICE,),
    )
    assert searches[0] == ("Keller forgetting college at the lake", (ALICE,))


def test_a_part_that_was_only_the_author_name_is_dropped():
    searches = _search_requests(
        _plan("Keller"),
        LibrarianBookRequestInput(current_line="Does Keller connect to this?"),
        (KELLER,),
    )
    assert searches == (("Does Keller connect to this?", (KELLER,)),)
