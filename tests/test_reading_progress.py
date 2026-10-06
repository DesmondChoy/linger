"""Issue #90: a declared chapter carries across turns, and never past the reader's word."""

import json

import pytest
from pydantic_ai.messages import UserPromptPart
from test_muse_tool_exposure import (
    BOOK_TOOLS,
    FINDING,
    NOTHING,
    Turns,
    _review,
    chat_turn,
    sessions,
)

from apps.backend import reading_progress
from apps.backend.schemas import ChatRequest

SESSION = "reading-progress"
T1 = (
    "I'm reading Alice's Adventures in Wonderland and I've just finished chapter 5, "
    "the one with the Caterpillar."
)
CAT = "What was Alice's answer to the Caterpillar?"
CH6 = "What was going on in the Duchess's kitchen with the baby and all that pepper?"
CH2_EVIDENCE = "pg11-v01b38ea4-ch02-ln0327-0360"
CH5_EVIDENCE = "pg11-v01b38ea4-ch05-ln0960-1016"


class Reader(Turns):
    def __init__(self, tmp_path, monkeypatch) -> None:
        super().__init__(tmp_path, monkeypatch)
        self.prior_evidence: list[list[str]] = []

    def say(self, message: str, *, outcome: str = "released"):
        reply = self.muse()

        def muse(messages, info):
            payload = json.loads(next(
                part.content for message in reversed(messages) for part in reversed(message.parts)
                if isinstance(part, UserPromptPart)
            ))
            self.prior_evidence.append([record["evidence_id"] for record in payload["prior_evidence"]])
            return reply(messages, info)

        if outcome == "failed":
            async def fail(*args, **kwargs):
                raise RuntimeError("provider down")

            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(chat_turn, "reflection_reply", fail)
                with pytest.raises(chat_turn.ChatTurnError):
                    self.run(muse, session_id=SESSION, message=message)
            return None
        provenance = _review("reject", findings=[FINDING]) if outcome == "declined" else None
        response = self.run(muse, session_id=SESSION, message=message, provenance=provenance)
        expected = "application_safe_decline" if outcome == "declined" else "muse_candidate"
        assert response.inspection.release.release_source == expected
        return response


@pytest.fixture
def reader(tmp_path, monkeypatch):
    yield Reader(tmp_path, monkeypatch)
    sessions.clear(SESSION)


def ceiling(response) -> int | None:
    return response.inspection.muse_turn["policy"]["spoiler_ceiling"]


def slot() -> int | str | None:
    progress = sessions.reading_progress(SESSION)
    if progress is None:
        return None
    return "retracted" if progress.chapter_max is None else progress.chapter_max


def offer_candidate(chapter: int) -> None:
    sessions.set_pending_clarification(SESSION, sessions.PendingClarification(
        book_id="pg11", book_title="Alice's Adventures in Wonderland", reason_code="insufficient_context",
    ))
    sessions.set_reading_candidate(SESSION, sessions.ReadingCandidate(
        book_id="pg11", book_title="Alice's Adventures in Wonderland", chapter=chapter,
    ))


def test_a_declared_chapter_carries_to_a_follow_up_question(reader) -> None:
    assert ceiling(reader.say(T1)) == 5
    follow_up = reader.say(CAT)
    assert follow_up.inspection.context_resolution["status"] == "confirmed"
    assert ceiling(follow_up) == 5


def test_a_carried_ceiling_does_not_force_the_book_tools(reader) -> None:
    reader.triage(NOTHING)
    reader.say(T1)
    reader.say(CAT)
    assert [offer["tools"] for offer in reader.offered] == [BOOK_TOOLS, []]


@pytest.mark.parametrize("message, chapter", [
    ("Sorry, I meant I've finished chapter 3.", 3),
    ("I'd only finished chapter 3.", 3),
    ("My mistake - I finished chapter 3, not 5.", 3),
    ("Actually I only finished chapter 4 — what did the Caterpillar say?", 4),
])
def test_a_lower_declaration_replaces_the_ceiling_at_once(reader, message, chapter) -> None:
    reader.say(T1)
    assert ceiling(reader.say(message)) == chapter
    assert slot() == chapter
    assert ceiling(reader.say(CAT)) == chapter


@pytest.mark.parametrize("message", [
    "Actually I'm only on chapter 3.",
    "Wait, I haven't finished chapter 5 yet.",
    "Hmm, I may have skipped a bit, not sure where I am.",
    "Scratch that, chapter three is where I stopped.",
    "I stopped at chapter 3.",
    "I only got as far as chapter 3.",
    "I'm not past chapter 3.",
    "I have not gotten past chapter 3.",
    "Correction: chapter 3, not 5.",
    "I misspoke, it was chapter 3.",
    "Chapter 3 is my limit.",
    "I'm at the pool of tears.",
    "I'm back on chapter 3.",
    "Only up to chapter 3, sorry.",
    "It's chapter 3, not 5.",
    "Can we stick to chapter 3?",
    "Hmm, I don't think I've actually read that far.",
    'I\'m only at "The Pool of Tears".',
    "Sorry, chapter 5 was a typo for 3.",
    'Wait, I\'m only up to "A Caucus-Race and a Long Tale".',
    'I said "chapter 5" but I meant 3.',
    'For Alice I\'m on "Down the Rabbit-Hole".',
    "Nope, 3.",
    "Actually, scratch the Caterpillar part, I haven't got there.",
    "I'm further now, chapter 7.",
    "Can you avoid anything after chapter 3?",
    "Could we not go beyond chapter 3?",
    "Please don't go past chapter 3?",
    "Would you keep to the first three chapters?",
    "Would you keep to the first 3 chapters?",
    "Hmm, did I really finish chapter 5? Maybe just 3.",
    "Can you stay within the first 3 chapters?",
    "Don't go further than chapter 3, okay?",
    "Could you stop at chapter 3?",
    "Can we keep it to chapter 3?",
    "Can you hold off on anything after chapter 3?",
    "Oh, I haven't met the Caterpillar.",
    "Wait, the Caterpillar hasn't happened for me yet.",
    "Please don't spoil the Caterpillar for me.",
    "Sorry, I was thinking of a different book.",
    "I lied about how far I'd read.",
    "Actually I'm still before the Caterpillar.",
    "I'm behind where I said.",
    "I exaggerated my progress earlier.",
    "Ugh, I confused it with the movie; I'm earlier than that.",
])
def test_unreadable_progress_talk_retracts_the_ceiling(reader, message) -> None:
    reader.say(T1)
    assert ceiling(reader.say(message)) is None
    assert slot() == "retracted"
    follow_up = reader.say(CAT)
    assert follow_up.inspection.context_resolution["status"] == "inferred"
    assert ceiling(follow_up) is None


@pytest.mark.parametrize("message", [
    "The Caterpillar scene in chapter 5 was so strange — why is he so rude?",
    "Why does the pool of tears matter for how Alice talks to the Caterpillar?",
    "Is chapter 5 the weirdest so far?",
    "I like how odd she is.",
    "I have two cats and they both hate the rain.",
    "We moved here three years ago and it still doesn't feel like home.",
    "I slept maybe five hours.",
])
def test_talk_about_the_book_keeps_the_carried_ceiling(reader, message) -> None:
    reader.say(T1)
    assert ceiling(reader.say(message)) == 5
    assert slot() == 5


def test_a_question_routed_to_another_work_is_not_carried(reader) -> None:
    reader.say(T1)
    assert ceiling(reader.say("What does Napoleon do with the puppies in Animal Farm?")) is None
    assert slot() == 5
    assert ceiling(reader.say(CAT)) == 5


def test_a_part_switch_replaces_the_ceiling(reader) -> None:
    reader.say("I'm reading The Story of My Life and I've finished chapter 10.")
    reader.say("I've finished Part III, Chapter 2.")
    follow_up = reader.say("What did she say about her teacher?")
    assert (follow_up.inspection.context_resolution["part_id"], ceiling(follow_up)) == ("part-iii", 2)


def test_a_declared_raise_applies_after_release(reader) -> None:
    reader.say(T1)
    assert ceiling(reader.say("Oops, I've actually finished chapter 7.")) == 7
    assert slot() == 7
    assert ceiling(reader.say(CH6)) == 7


@pytest.mark.parametrize("outcome", ["declined", "failed"])
@pytest.mark.parametrize("message, after", [
    ("Sorry, I meant I've finished chapter 3.", 3),
    ("Correction: chapter 3, not 5.", "retracted"),
    ("I've finished chapter 7.", 5),
])
def test_only_a_released_turn_raises_but_any_turn_lowers(reader, outcome, message, after) -> None:
    reader.say(T1)
    reader.say(message, outcome=outcome)
    assert slot() == after


@pytest.mark.parametrize("outcome, after", [("released", 3), ("declined", "retracted")])
def test_an_answer_after_a_retraction_waits_for_release(reader, outcome, after) -> None:
    reader.say(T1)
    reader.say("I misspoke, it was chapter 3.")
    sessions.set_pending_clarification(SESSION, sessions.PendingClarification(
        book_id="pg11", book_title="Alice's Adventures in Wonderland", reason_code="insufficient_context",
    ))
    reader.say("3", outcome=outcome)
    assert slot() == after


def test_a_staged_raise_does_not_overwrite_a_retraction_made_meanwhile(reader) -> None:
    reader.say(T1)
    request = ChatRequest(session_id=SESSION, message="I've finished chapter 7.")
    _, pending, _ = reading_progress.apply(
        request, chat_turn.resolve_reading_context(request),
        parser_patterns=(chat_turn.IN_PROGRESS_PATTERN, chat_turn.COMPLETION_PATTERN, chat_turn.READ_NAMED_PATTERN),
    )
    reader.say("Actually I'm only on chapter 3.")
    reading_progress.commit(SESSION, pending, "muse_candidate")
    assert slot() == "retracted"


def test_a_retraction_supersedes_earlier_reader_statements(reader) -> None:
    reader.say(T1)
    reader.say("I like how odd she is.")
    reader.say("Actually I'm only on chapter 3.")
    assert [statement.statement_id for statement in sessions.reader_statements(SESSION)] == ["reader-3"]


@pytest.mark.parametrize("message, visible", [
    ("Sorry, I meant I've finished chapter 3.", [CH2_EVIDENCE]),
    ("Actually I'm only on chapter 3.", []),
])
def test_earlier_evidence_follows_the_lowered_ceiling(reader, message, visible) -> None:
    reader.say(T1)
    sessions.append_turn(
        SESSION, CAT, "She said she hardly knew.", turn_id="cited",
        release_source="muse_candidate", evidence_ids=(CH5_EVIDENCE, CH2_EVIDENCE),
    )
    reader.say(message)
    assert reader.prior_evidence[-1] == visible


def test_a_reading_candidate_answers_only_the_next_turn(reader) -> None:
    reader.say(T1)
    reader.say("Actually I'm only on chapter 3.")
    offer_candidate(9)
    reader.say("I like how odd she is.")
    assert sessions.reading_candidate(SESSION) is None
    assert ceiling(reader.say("Yes, exactly!")) is None


def test_a_failed_turn_does_not_restore_a_reading_candidate(reader) -> None:
    offer_candidate(9)
    reader.say("I like how odd she is.", outcome="failed")
    assert sessions.reading_candidate(SESSION) is None


def test_switching_books_drops_the_ceiling_without_superseding_statements(reader) -> None:
    reader.say(T1)
    reader.say("I'm reading Animal Farm.")
    assert slot() is None
    assert [statement.statement_id for statement in sessions.reader_statements(SESSION)] == [
        "reader-1", "reader-2",
    ]


@pytest.mark.parametrize("message", [
    'My friend said "I\'ve finished chapter 12". Anyway, what happens next?',
    "The forum says `I've finished chapter 12`. What did the Caterpillar say?",
    (
        "I'm reading Alice's Adventures in Wonderland.\n> I've finished chapter 12\n"
        "That's what the forum post said. What did the Caterpillar say?"
    ),
    (
        "I'm reading Alice's Adventures in Wonderland.\n```\nI've finished chapter 12\n```\n"
        "What did the Caterpillar say?"
    ),
    "My friend wrote 'I have finished chapter 12' on her blog.",
    "My friend wrote ‘I have finished chapter 12’ on her blog.",
    "From the forum: «I've finished chapter 12»",
    'She posted:\n"Big news.\nI\'ve finished chapter 12!"',
    "My friend texted “I’ve finished chapter 12.\n“And the ending was wild,” she added.",
    "My friend texted “I’ve finished chapter 12 and the “twist” is wild” lol",
    "My friend wrote ‘I have finished chapter 12 and the ‘twist’ is wild’ on her blog.",
    (
        "She wrote ‘" + "It was a long and winding season of reading, slow and patient. " * 6
        + "I’ve finished chapter 12, and nothing was the same.’ on her blog."
    ),
])
def test_quoted_progress_retracts_but_never_raises(reader, message) -> None:
    reader.say(T1)
    assert ceiling(reader.say(message)) is None
    assert slot() == "retracted"


def test_a_restart_hides_restored_statements_from_boundary_judgement(reader) -> None:
    reader.say(T1)
    reader.say("Actually I'm only on chapter 3.")
    history = sessions.history(SESSION)
    turns = [(request.parts[0].content, reply.parts[0].content) for request, reply in zip(history[::2], history[1::2])]
    sessions.clear(SESSION)
    sessions.restore_history(SESSION, turns)
    assert sessions.reader_statements(SESSION) == ()
    reader.say("I like how odd she is.")
    assert [statement.statement_id for statement in sessions.reader_statements(SESSION)] == ["reader-3"]
