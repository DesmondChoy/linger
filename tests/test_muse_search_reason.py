"""Muse's `librarian_search` shows a fixed reason for a `sufficient` result, and Librarian's own otherwise."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.backend.contracts import BookScope, EvidenceBundle
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.muse import tools as muse_tools
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian
from src.linger.contracts.librarian import ClarificationRequest, RetrievalFailure
from src.linger.contracts.turn import ConfirmedReading
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.orchestration import turn_context
from src.linger.orchestration.grounding import grounding_evidence
from tests.test_librarian_stated_answers import (
    EGGS, EGGS_RECORD, HOOKAH, LINE, NECK, NECK_RECORD, REASON, VERSION, WORK_ID, LibrarianScript,
)

CONFIRMED = ConfirmedReading(work_id=WORK_ID, chapter_max=5)
LIMITATION = "Only part of the reasoning is present."


def muse_search(script: LibrarianScript, *, reading=CONFIRMED, retrieval_error=None):
    """Call Muse's tool over the real grounding path with a scripted Librarian.

    Returns what Muse received, what grounding judged, and the turn's ledgers.
    """
    librarian = MagicMock()
    librarian.retrieve_for_judgement.return_value = EvidenceBundle(items=[HOOKAH, EGGS, NECK], retrieval_note="")
    librarian.retrieve_for_judgement.side_effect = retrieval_error
    judged = []

    async def grounding(request):
        judged.append(await grounding_evidence(request, librarian=librarian))
        return judged[-1]

    message = turn_context.set_reader_message(LINE)
    confirmed = turn_context.set_confirmed_reading(reading)
    ledger = turn_context.set_turn_evidence(())
    try:
        with (
            patch("src.linger.agents.librarian.agent.librarian_agent", script.agent()),
            patch("src.linger.agents.muse.tools.grounding_evidence", grounding),
        ):
            shown = asyncio.run(muse_tools.librarian_search(WORK_ID, VERSION))
        return shown, judged[0], dict(turn_context.turn_evidence()), turn_context.turn_stated_answers()
    finally:
        turn_context.reset_turn_evidence(ledger)
        turn_context.reset_confirmed_reading(confirmed)
        turn_context.reset_reader_message(message)


def test_a_sufficient_result_reaches_muse_with_the_fixed_reason_and_everything_else_intact():
    shown, judged, evidence_ledger, answer_ledger = muse_search(LibrarianScript())

    assert judged.strength_reason == REASON
    assert shown.strength_reason == muse_tools.SUFFICIENT_STRENGTH_REASON != REASON
    assert shown == judged.model_copy(update={"strength_reason": muse_tools.SUFFICIENT_STRENGTH_REASON})
    assert REASON not in shown.model_dump_json()
    assert (shown.evidence_strength, shown.evidence, shown.limitations) == (
        "sufficient", (EGGS_RECORD, NECK_RECORD), (),
    )
    assert len(shown.stated_answers) == 3
    # The ledgers are what the judged search registered.
    assert evidence_ledger == {EGGS.evidence_id: EGGS_RECORD, NECK.evidence_id: NECK_RECORD}
    assert answer_ledger == judged.stated_answers


def test_the_fixed_reason_is_one_application_sentence_not_derived_from_the_result():
    shown, judged, _, _ = muse_search(LibrarianScript())

    assert shown.strength_reason == "The selected records were judged sufficient for the reader's request."
    # None of the judged reason's content, nor the selected records', is carried over.
    assert judged.strength_reason == "The selected passages give the Pigeon's reasons."
    lowered = shown.strength_reason.lower()
    assert not [word for word in ("pigeon", "reasons", "passages", "alice", "serpent", "eggs", "neck")
                if word in lowered]


class SufficientWithLimitations(LibrarianScript):
    """A Librarian whose `sufficient` assessment still names a limitation."""

    def respond(self, messages, info):
        response = super().respond(messages, info)
        if self.kinds()[-1] == "assessment":
            response.parts[0].args["limitations"] = [LIMITATION]
        return response


def test_a_sufficient_result_keeps_its_limitations_verbatim():
    shown, judged, _, _ = muse_search(SufficientWithLimitations())

    assert (shown.evidence_strength, shown.strength_reason) == ("sufficient", muse_tools.SUFFICIENT_STRENGTH_REASON)
    assert shown.limitations == judged.limitations == (LIMITATION,)


def test_a_weak_result_keeps_the_librarian_reason_and_limitations_verbatim():
    shown, judged, evidence_ledger, answer_ledger = muse_search(LibrarianScript(strength="weak"))

    assert shown is judged
    assert (shown.evidence_strength, shown.strength_reason, shown.limitations) == ("weak", REASON, (LIMITATION,))
    assert set(evidence_ledger) == {EGGS.evidence_id, NECK.evidence_id}
    assert answer_ledger == shown.stated_answers


def test_a_result_judged_none_is_returned_unchanged():
    shown, judged, evidence_ledger, _ = muse_search(LibrarianScript(strength="none"))

    assert shown is judged
    assert (shown.outcome, shown.evidence_strength, shown.strength_reason) == ("no_evidence", "none", REASON)
    assert evidence_ledger == {}


@pytest.mark.parametrize("arguments,kind", [
    ({"reading": None}, ClarificationRequest),
    ({"retrieval_error": RuntimeError("index unavailable")}, RetrievalFailure),
], ids=["clarification", "failure"])
def test_a_clarification_and_a_failure_are_returned_unchanged(arguments, kind):
    shown, judged, _, _ = muse_search(LibrarianScript(), **arguments)

    assert isinstance(shown, kind)
    assert shown is judged


def test_the_librarian_recorded_exchange_keeps_its_full_reason():
    recorder = SceneTranscriptRecorder()

    with bind_evaluation_transcript_sink(recorder):
        shown, _, _, _ = muse_search(LibrarianScript())

    assessment, = (e for e in recorder.exchanges if (e.role, e.stage) == ("Librarian", "evidence_strength"))
    assert assessment.output["strength_reason"] == REASON
    assert shown.strength_reason == muse_tools.SUFFICIENT_STRENGTH_REASON


def test_serendipity_book_search_still_carries_the_librarian_reason():
    scope = BookScope(work_id=WORK_ID, book_version_id=VERSION, chapter_max=5)
    librarian = MagicMock()
    librarian.retrieve_for_judgement.return_value = EvidenceBundle(items=[HOOKAH, EGGS, NECK], retrieval_note="")
    deps = SerendipityDependencies(
        task=ConnectionDiscoveryInput(
            cue=LINE, intent="find_connection", presentation="ask_before_showing",
            scope=ConnectionScope(allowed_sources=("book_corpus",), book_scopes=(scope,)),
        ),
        librarian=librarian,
    )

    with patch("src.linger.agents.librarian.agent.librarian_agent", LibrarianScript().agent()):
        result = asyncio.run(search_librarian(SimpleNamespace(deps=deps)))

    assert (result.judgement.evidence_strength, result.judgement.strength_reason) == ("sufficient", REASON)
