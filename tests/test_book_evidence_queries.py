"""A search in an author's book drops the author's name, which only names the book."""

from src.linger.orchestration.book_evidence import _without_author

KELLER = "pg2397"
ALICE = "pg11"


def test_the_author_name_is_removed_from_a_search_of_their_book():
    assert _without_author("Keller forgetting all about college at the lake", KELLER) == (
        "forgetting all about college at the lake"
    )


def test_full_name_and_possessive_are_removed():
    assert _without_author("Helen Keller at the lake", KELLER) == "at the lake"
    assert _without_author("Keller's teacher spelling water", KELLER) == "teacher spelling water"


def test_names_of_other_books_authors_are_left_alone():
    assert _without_author("Keller forgetting college at the lake", ALICE) == (
        "Keller forgetting college at the lake"
    )


def test_a_query_that_was_only_the_author_name_is_kept():
    assert _without_author("Keller", KELLER) == "Keller"
