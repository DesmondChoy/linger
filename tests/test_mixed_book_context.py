"""Reader declarations preserve chapter labels and exact named locations."""
from unittest.mock import patch

import pytest

from apps.backend import chat_turn, sessions
from apps.backend.config import Settings
from apps.backend.schemas import ChatRequest
from apps.backend.librarian import Librarian


@pytest.fixture(autouse=True)
def mixed_session():
    settings = Settings(_env_file=None, linger_model="google:gemini-2.5-flash")
    with patch.object(chat_turn, "settings", settings), patch.object(chat_turn, "librarian_service", Librarian()):
        yield
    sessions.clear("mixed-context")


def resolve(message):
    return chat_turn.resolve_reading_context(ChatRequest(session_id="mixed-context", message=message))


def test_douglass_chapter_one_is_not_preface():
    context = resolve("I've finished Chapter 1 of Frederick Douglass.")
    assert context.status == "confirmed"
    assert context.work_id == "pg23"
    assert context.chapter_max == 1
    assert context.part_id == "main"
    assert context.unit_ids == ()


def test_keller_part_is_preserved_and_chapters_restart():
    resolve("The Story of My Life")
    first = resolve("I've finished Chapter 3.")
    assert (first.part_id, first.chapter_max) == ("main", 3)
    supplementary = resolve("I've finished Part III, Chapter 1.")
    assert (supplementary.part_id, supplementary.chapter_max) == ("part-iii", 1)
    next_chapter = resolve("I've finished Chapter 2.")
    assert (next_chapter.part_id, next_chapter.chapter_max) == ("part-iii", 2)
    merely_selected = resolve("I'm in Part I.")
    assert merely_selected.chapter_max is None
    assert merely_selected.unit_ids == ()


def test_unknown_chapter_and_letter_ambiguity_do_not_authorize_reading():
    resolve("The Story of My Life")
    context = resolve("I've finished Part III, Chapter 9.")
    assert context.status == "inferred"
    assert context.chapter_max is None
    ambiguous = resolve("I've finished the letter to Mrs. Kate Adams Keller.")
    assert ambiguous.clarification_question
    assert not ambiguous.unit_ids


def test_named_letter_grants_only_that_letter_and_propagates_to_muse():
    resolve("The Story of My Life")
    request = ChatRequest(session_id="mixed-context", message="I read the letter to Dr. Alexander Graham Bell, November, 1887.")
    context = chat_turn.resolve_reading_context(request)
    assert context.status == "confirmed"
    assert context.part_id == "letters"
    assert context.chapter_max is None
    assert context.unit_ids == ("pg2397-vb3cc1e13-sec032",)
    inspection, _, review = chat_turn.prepare_reflection_turn(request, allow_memory_capture=False, resolution=context)
    assert inspection.muse_turn["reading_context"]["unit_ids"] == list(context.unit_ids)
    assert review["reading_context"]["unit_ids"] == list(context.unit_ids)
    assert inspection.muse_turn["policy"]["allow_retrieval"] is True


def test_unsupported_or_multiple_parts_never_fall_back_to_main():
    resolve("The Story of My Life")
    for message in ("I've finished Part IV, Chapter 1.", "I've finished Part I Chapter 1 and Part III Chapter 1."):
        context = resolve(message)
        assert context.status == "inferred"
        assert context.chapter_max is None
        assert context.clarification_question


def test_reading_about_a_letter_does_not_authorize_the_letter():
    resolve("The Story of My Life")
    context = resolve("I read about the letter to Dr. Alexander Graham Bell, November, 1887.")
    assert not context.unit_ids
    assert context.chapter_max is None


@pytest.mark.parametrize("message", [
    "I've finished Chapter 1. Tell me about Part III.",
    "I've finished Chapter 1, tell me about Part III.",
    "I've finished Chapter 1 and would like to discuss Part III.",
])
def test_later_question_cannot_change_the_completed_chapter_part(message):
    resolve("The Story of My Life")
    context = resolve(message)
    assert (context.status, context.part_id, context.chapter_max) == ("confirmed", "main", 1)


@pytest.mark.parametrize("message", [
    "I've finished lunch. Tell me about the letter to Alexander Graham Bell, November 1887.",
    "I've finished lunch. What happens in Chapter 5?",
    "I've finished lunch and can you explain Chapter 5?",
])
def test_unrelated_completion_does_not_grant_a_queried_location(message):
    resolve("The Story of My Life")
    context = resolve(message)
    assert context.chapter_max is None
    assert not context.unit_ids


@pytest.mark.parametrize("message", [
    "I read the preface of Frederick Douglass.",
    "I finished the preface of Frederick Douglass.",
    "I've finished the preface of Frederick Douglass.",
])
def test_book_title_cannot_make_a_named_preface_ambiguous(message):
    context = resolve(message)
    assert context.status == "confirmed"
    assert context.unit_ids == ("pg23-vd3f08ac3-sec01",)


@pytest.mark.parametrize("message", [
    "I've finished Chapter 1 of Part III of The Story of My Life.",
    "I finished Part III, Chapter 1 of The Story of My Life.",
])
def test_completed_part_chapter_and_title_accept_natural_ordering(message):
    context = resolve(message)
    assert (context.status, context.part_id, context.chapter_max) == ("confirmed", "part-iii", 1)


def test_plain_past_tense_can_complete_a_dated_letter():
    resolve("The Story of My Life")
    context = resolve("I finished the letter to Alexander Graham Bell, November 1887.")
    assert context.unit_ids == ("pg2397-vb3cc1e13-sec032",)


@pytest.mark.parametrize("message", [
    "I've finished the preface and the letter to Alexander Graham Bell, November 1887.",
    "I read the letter to Alexander Graham Bell, November 1887, and the dedication.",
])
def test_multiple_named_locations_clarify_instead_of_selecting_the_dated_one(message):
    resolve("The Story of My Life")
    context = resolve(message)
    assert context.clarification_question
    assert not context.unit_ids
    assert context.chapter_max is None


def test_named_letter_cannot_override_an_explicit_conflicting_part():
    resolve("The Story of My Life")
    context = resolve("I've finished Part III, the letter to Alexander Graham Bell, November 1887.")
    assert context.clarification_question
    assert context.chapter_max is None
    assert not context.unit_ids


@pytest.mark.parametrize("message, unit_id", [
    ("I finished the editor's preface.", "pg2397-vb3cc1e13-sec002"),
    ("I read the introduction to the letters.", "pg2397-vb3cc1e13-sec026"),
])
def test_named_editorial_material_uses_its_displayed_label(message, unit_id):
    resolve("The Story of My Life")
    context = resolve(message)
    assert context.unit_ids == (unit_id,)


def test_unknown_book_qualifier_cannot_reuse_the_selected_books_preface():
    resolve("The Story of My Life")
    context = resolve("I read the preface of The Unregistered Notebook.")
    assert context.status == "unknown"
    assert context.unit_ids == ()
    assert sessions.book_selection("mixed-context") is None


@pytest.mark.parametrize("message", [
    "I've finished Chapter 1, not Part III Chapter 1.",
    "I read the letter to Alexander Graham Bell about Chapter 5.",
])
def test_multiple_selectors_never_authorize_a_chapter(message):
    resolve("The Story of My Life")
    context = resolve(message)
    assert context.clarification_question
    assert context.chapter_max is None
    assert context.unit_ids == ()
