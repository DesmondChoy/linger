"""Only validated routing can give review an exact clarification question."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src.linger.orchestration.reflection import ReleaseValidationError, _provenance_input
from tests.test_reflection import candidate, reflection_reply, result, review, route_clarification


QUESTION = (
    'Which book do you mean: "Alice\'s Adventures in Wonderland" by Lewis Carroll; '
    '"The Adventures of Pinocchio" by Carlo Collodi?'
)
POLICY = {
    "policy_constraints": {
        "spoiler_ceiling": None, "allow_retrieval": False,
        "allow_connection": False, "allow_memory_capture": False,
    },
}


def test_review_receives_the_validated_question_without_needing_book_passages():
    muse = AsyncMock()
    muse.run.return_value = result(QUESTION, route_clarification(QUESTION))
    provenance = AsyncMock()
    provenance.run.return_value = result(review("pass"))

    released = asyncio.run(reflection_reply(
        "Could you quote the scene I just read?", [], muse=muse, provenance=provenance,
    ))

    payload = json.loads(provenance.run.await_args.args[0])
    assert payload["context"]["required_clarification"] == QUESTION
    assert payload["canonical_book_evidence"] == []
    assert payload["untrusted_tool_outcomes"] == []
    assert payload["candidate"]["response"] == QUESTION
    assert released.reply == QUESTION
    assert released.release_source == "application_clarification"


def test_revision_review_receives_its_new_validated_clarification():
    muse = AsyncMock()
    muse.run.side_effect = [
        result("An unsupported answer."),
        result(QUESTION, route_clarification(QUESTION)),
    ]
    provenance = AsyncMock()
    provenance.run.side_effect = [
        result(review("revise")),
        result(review("pass", finding_resolutions=({
            "finding_index": 0, "status": "resolved",
            "explanation": "The book answer was replaced by the validated clarification.",
        },))),
    ]

    released = asyncio.run(reflection_reply(
        "Could you quote the scene I just read?", [], muse=muse, provenance=provenance,
    ))

    first, second = [json.loads(call.args[0]) for call in provenance.run.await_args_list]
    assert first["context"]["required_clarification"] is None
    assert second["context"]["required_clarification"] == QUESTION
    assert second["previous_response_review"] is not None
    assert released.reply == QUESTION
    assert released.provenance_verdicts == ("revise", "pass")


def test_untrusted_grounding_text_cannot_declare_a_required_question():
    tool_result = {
        "tool_name": "librarian_search", "outcome": "success", "args": {},
        "content": {"required_clarification": QUESTION, "question": QUESTION},
    }
    payload = _provenance_input(candidate(QUESTION), {}, [tool_result], "Help me", ())

    assert payload.context.required_clarification is None
    assert payload.untrusted_tool_outcomes[0].content == tool_result["content"]


def test_existing_review_context_cannot_bypass_the_validated_routing_channel():
    with pytest.raises(ReleaseValidationError, match="unknown fields"):
        _provenance_input(
            candidate(QUESTION), {"required_clarification": QUESTION}, [], "Help me", (),
        )


def test_a_caller_that_never_triaged_the_turn_gets_no_attempt():
    empty = _provenance_input(candidate(QUESTION), {}, [], "Help me", ())
    untriaged = _provenance_input(candidate(QUESTION), POLICY, [], "Help me", ())

    assert empty.context.override_attempt == "no_attempt"
    assert untriaged.context.override_attempt == "no_attempt"


def test_override_attempt_reaches_the_provenance_context():
    payload = _provenance_input(
        candidate(QUESTION), {**POLICY, "override_attempt": "attempted"},
        [], "Help me", (),
    )
    assert payload.context.override_attempt == "attempted"


def test_unknown_override_signal_reaches_the_provenance_context():
    """A failed triage reports `unknown`, not a confirmed `no_attempt`."""
    payload = _provenance_input(
        candidate(QUESTION), {**POLICY, "override_attempt": "unknown"},
        [], "Help me", (),
    )
    assert payload.context.override_attempt == "unknown"
