"""Muse's `librarian_search` shows a fixed reason for a `sufficient` result, and Librarian's own otherwise."""

import asyncio
import json
import zlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.config import get_settings
from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import BookRequestPart, BookRequestPlan
from src.linger.agents.muse import tools as muse_tools
from src.linger.agents.serendipity.models import ConnectionDiscoveryInput, ConnectionScope
from src.linger.agents.serendipity.tools import SerendipityDependencies, search_librarian
from src.linger.contracts.librarian import ClarificationRequest, RetrievalFailure
from src.linger.contracts.turn import ConfirmedReading
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.orchestration import turn_context
from src.linger.orchestration.book_evidence import evidence_record_from_item
from src.linger.orchestration.grounding import grounding_evidence

WORK_ID = "pg11"
VERSION = get_settings().allowed_book_version_ids[0]
QUESTION = "Why does the Pigeon insist that Alice is a serpent?"
LINE = f"I've finished chapter 5. {QUESTION}"
REASON = "The selected passages give the Pigeon's reasons."
CONFIRMED = ConfirmedReading(work_id=WORK_ID, chapter_max=5)
LIMITATION = "Only part of the reasoning is present."


def item(identity: str, text: str) -> EvidenceItem:
    start = zlib.crc32(identity.encode()) % 100_000 * 10
    return EvidenceItem(
        evidence_id=f"{VERSION}-{identity}", work_id=WORK_ID, book_version_id=VERSION,
        chapter_id=f"{VERSION}-ch05", chapter=5, location=f"Chapter 5, {identity}",
        source_title="Alice's Adventures in Wonderland", source_sha256="a" * 64,
        source_lines=(start, start + 1), excerpt=text, relevance=0.9,
    )


HOOKAH = item("hookah", "The Caterpillar smoked its hookah in silence.")
EGGS = item("eggs", "Alice admitted she had tasted eggs.")
NECK = item("neck", "The Pigeon had never seen a girl with such a neck as that.")
EGGS_RECORD, NECK_RECORD = (evidence_record_from_item(i) for i in (EGGS, NECK))
PLAN = BookRequestPlan(parts=(BookRequestPart(context_spans=(), purpose="answer", reader_spans=(QUESTION,)),))


class LibrarianScript:
    """One scripted Librarian model that plans and assesses."""

    def __init__(self, *, strength="sufficient", selected=(EGGS, NECK)):
        self.strength, self.selected = strength, selected
        self.calls: list[tuple[str, dict]] = []

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]

    def respond(self, messages, info):
        payload = json.loads(next(
            part.content for message in messages for part in message.parts
            if isinstance(part, UserPromptPart)
        ))
        kind = "plan" if "current_line" in payload else "assessment"
        self.calls.append((kind, payload))
        if kind == "plan":
            output = PLAN.model_dump(mode="json")
        else:
            labels = {record["text"]: record["evidence_id"] for record in payload["evidence"]}
            chosen = [labels[selected.excerpt] for selected in self.selected] if self.strength != "none" else []
            output = {
                "evidence_strength": self.strength, "strength_reason": REASON,
                "relevant_evidence_ids": chosen,
                "limitations": [LIMITATION] if self.strength == "weak" else [],
                "support": [{"evidence_id": label, "part_index": 0, "necessary_support": "States a reason."}
                            for label in chosen],
                "additional_parts": [],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def agent(self):
        return build_librarian_agent(FunctionModel(self.respond))


def muse_search(script: LibrarianScript, *, reading=CONFIRMED, retrieval_error=None):
    """Call Muse's tool over the real grounding path with a scripted Librarian.

    Returns what Muse received, what grounding judged, and the turn's evidence ledger.
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
        return shown, judged[0], dict(turn_context.turn_evidence())
    finally:
        turn_context.reset_turn_evidence(ledger)
        turn_context.reset_confirmed_reading(confirmed)
        turn_context.reset_reader_message(message)


def test_a_sufficient_result_reaches_muse_with_the_fixed_reason_and_everything_else_intact():
    shown, judged, evidence_ledger = muse_search(LibrarianScript())

    assert judged.strength_reason == REASON
    assert shown.strength_reason == muse_tools.SUFFICIENT_STRENGTH_REASON != REASON
    assert shown == judged.model_copy(update={"strength_reason": muse_tools.SUFFICIENT_STRENGTH_REASON})
    assert REASON not in shown.model_dump_json()
    assert (shown.evidence_strength, shown.evidence, shown.limitations) == (
        "sufficient", (EGGS_RECORD, NECK_RECORD), (),
    )
    # The ledger is what the judged search registered.
    assert evidence_ledger == {EGGS.evidence_id: EGGS_RECORD, NECK.evidence_id: NECK_RECORD}


def test_the_fixed_reason_is_one_application_sentence_not_derived_from_the_result():
    shown, judged, _ = muse_search(LibrarianScript())

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
    shown, judged, _ = muse_search(SufficientWithLimitations())

    assert (shown.evidence_strength, shown.strength_reason) == ("sufficient", muse_tools.SUFFICIENT_STRENGTH_REASON)
    assert shown.limitations == judged.limitations == (LIMITATION,)


def test_a_weak_result_keeps_the_librarian_reason_and_limitations_verbatim():
    shown, judged, evidence_ledger = muse_search(LibrarianScript(strength="weak"))

    assert shown is judged
    assert (shown.evidence_strength, shown.strength_reason, shown.limitations) == ("weak", REASON, (LIMITATION,))
    assert set(evidence_ledger) == {EGGS.evidence_id, NECK.evidence_id}


def test_a_result_judged_none_is_returned_unchanged():
    shown, judged, evidence_ledger = muse_search(LibrarianScript(strength="none"))

    assert shown is judged
    assert (shown.outcome, shown.evidence_strength, shown.strength_reason) == ("no_evidence", "none", REASON)
    assert evidence_ledger == {}


@pytest.mark.parametrize("arguments,kind", [
    ({"reading": None}, ClarificationRequest),
    ({"retrieval_error": RuntimeError("index unavailable")}, RetrievalFailure),
], ids=["clarification", "failure"])
def test_a_clarification_and_a_failure_are_returned_unchanged(arguments, kind):
    shown, judged, _ = muse_search(LibrarianScript(), **arguments)

    assert isinstance(shown, kind)
    assert shown is judged


def test_the_librarian_recorded_exchange_keeps_its_full_reason():
    recorder = SceneTranscriptRecorder()

    with bind_evaluation_transcript_sink(recorder):
        shown, _, _ = muse_search(LibrarianScript())

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
