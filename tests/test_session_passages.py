"""Reader-history handoff and exact-passage authorization regressions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_librarian_route_e2e import (
    ChatRequest,
    FunctionModel,
    _muse_routes_then_relays_clarification,
    _last_tool_return,
    _no_memory,
    _provenance_pass_capturing,
    _sufficient_strength,
    _plain_reply_model,
    _provenance_pass,
    chat_turn,
    muse_chat_agent,
    provenance_agent,
    sessions,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from apps.backend.contracts import EvidenceBundle, EvidenceItem
from apps.backend.librarian import Librarian
from src.linger.agents.librarian.models import BoundaryInferenceDecision, PassageInferenceDecision
from src.linger.contracts.emotional import EmotionalBoundaryAssessment
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.turn_context import confirmed_reading, passage_grant
from src.linger.services.memory import AccountContext, MemoryPolicyService

FIRST_LINE = (
    "Got up to the part with the caterpillar on the mushroom tonight. It keeps "
    "asking Alice who she is and she can't answer properly. I had to put the "
    "book down for a minute. Reading two chapters a night if I can stay awake."
)
SECOND_LINE = (
    "There's a bit where Alice tries to tell the caterpillar that she can't "
    "explain herself because she isn't herself at the moment. I've been turning "
    "it over all week but I know I'm mangling the actual wording. What does she "
    "actually say there?"
)
QUOTE_ID = "pg11-v01b38ea4-ch05-ln0974-0975"


def private_candidates(request):
    if request.purpose != "boundary_inference":
        raise AssertionError("Passage grounding must not search beyond the exact grant")
    record = Librarian().fetch_by_id("pg11-v01b38ea4-ch05-ln0960-1016")
    return EvidenceBundle(items=[EvidenceItem(
        evidence_id=record.evidence_id, work_id=record.work_id,
        book_version_id=record.book_version_id, chapter_id=record.chapter_id,
        source_title="Alice's Adventures in Wonderland", location=record.location,
        chapter=record.chapter_number, source_sha256=record.source_sha256,
        source_lines=record.source_lines, excerpt=record.text, relevance=0.95,
    )], retrieval_note="Deterministic private candidate window from the real corpus")


class SessionPassageChatTests(unittest.IsolatedAsyncioTestCase):
    session_id = "session-passage-test"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(sessions.clear, self.session_id)
        self.service = MemoryPolicyService(Path(directory.name))
        self.account = AccountContext("session-passage-account")
        self.service.set_capture_enabled(self.account, False)
        preflight = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            return_value=EmotionalBoundaryAssessment(decision="continue_reflection"),
        )
        preflight.start()
        self.addCleanup(preflight.stop)
        retrieval = patch.object(librarian_service, "retrieve", side_effect=private_candidates)
        retrieval.start()
        self.addCleanup(retrieval.stop)

    async def first_turn(self):
        with (
            muse_chat_agent.override(model=FunctionModel(_plain_reply_model("Take your time tonight."))),
            provenance_agent.override(model=FunctionModel(_provenance_pass)),
        ):
            response = await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=FIRST_LINE),
                self.service,
                self.account,
            )
        self.assertEqual("muse_candidate", response.inspection.release.release_source)

    async def test_private_librarian_receives_prior_original_reader_line(self):
        await self.first_turn()
        calls = []

        async def judge(*args):
            calls.append(args)
            return BoundaryInferenceDecision(
                outcome="uncertain", confidence=0.3, reason_code="insufficient_context"
            )

        with (
            patch("src.linger.orchestration.boundary.judge_spoiler_boundary", side_effect=judge),
            muse_chat_agent.override(model=FunctionModel(_muse_routes_then_relays_clarification())),
            provenance_agent.override(model=FunctionModel(_provenance_pass)),
        ):
            await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=SECOND_LINE),
                self.service,
                self.account,
            )
        self.assertEqual(1, len(calls))
        self.assertEqual(4, len(calls[0]), "Librarian is missing the reader-history input")
        self.assertEqual([FIRST_LINE], [line.text for line in calls[0][3]])
        self.assertEqual((), calls[0][1], "Session continuity must not require saved memories")

    async def test_two_messages_release_exact_quote_without_completed_chapter(self):
        await self.first_turn()
        observed = []
        reviews = []

        async def judge(line, memories, paragraphs, statements):
            self.assertEqual(SECOND_LINE, line)
            self.assertEqual([FIRST_LINE], [statement.text for statement in statements])
            self.assertIn(QUOTE_ID, {record.evidence_id for record in paragraphs})
            return PassageInferenceDecision(
                outcome="passages", work_id="pg11", book_version_id="pg11-v01b38ea4",
                confidence=0.98, authorization_basis="session_supported",
                supporting_statement_ids=(statements[0].statement_id,),
                supporting_evidence_ids=(QUOTE_ID,), passage_evidence_ids=(QUOTE_ID,),
            )

        def muse(messages, info):
            routed = _last_tool_return(messages, "librarian_route")
            if routed is None:
                return ModelResponse(parts=[ToolCallPart("librarian_route", {})])
            searched = _last_tool_return(messages, "librarian_search")
            if searched is None:
                observed.append(routed)
                self.assertIsNone(confirmed_reading())
                self.assertEqual((QUOTE_ID,), passage_grant().scope.evidence_ids)
                return ModelResponse(parts=[ToolCallPart("librarian_search", {
                    "query": SECOND_LINE, "work_id": routed["work_id"],
                    "book_version_id": routed["book_version_id"], "reading_boundary": None,
                })])
            observed.append(searched)
            record = searched["evidence"][0]
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "reply": record["text"], "memory": _no_memory(),
                "evidence_uses": [{"source_kind": "book_corpus", "evidence_id": record["evidence_id"],
                    "source_location": record["location"], "exact_quote": record["text"]}],
            })])

        with (
            patch("src.linger.orchestration.boundary.judge_spoiler_boundary", side_effect=judge),
            patch("src.linger.orchestration.grounding.judge_evidence_strength", side_effect=_sufficient_strength),
            muse_chat_agent.override(model=FunctionModel(muse)),
            provenance_agent.override(model=FunctionModel(_provenance_pass_capturing(reviews))),
        ):
            response = await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=SECOND_LINE), self.service, self.account,
            )
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(Librarian().fetch_by_id(QUOTE_ID).text, response.reply)
        self.assertEqual("passages", observed[0]["kind"])
        self.assertEqual("session_supported", observed[0]["authorization_basis"])
        self.assertNotIn("max_chapter_inclusive", observed[0])
        self.assertEqual([QUOTE_ID], reviews[0]["context"]["passage_scope"]["evidence_ids"])
        self.assertIsNone(reviews[0]["context"]["reading_context"])
        self.assertIsNone(reviews[0]["context"]["policy"]["spoiler_ceiling"])
        self.assertEqual((QUOTE_ID,), sessions.released_evidence_ids(self.session_id))
        self.assertEqual(4, len(sessions.history(self.session_id)))
        self.assertIsNone(sessions.reading_candidate(self.session_id))
        self.assertIsNone(sessions.pending_clarification(self.session_id))
        self.assertIsNone(passage_grant())
        self.assertEqual(0, len(self.service.list_active(self.account)))

    async def test_film_statement_does_not_release_a_passage(self):
        with (
            muse_chat_agent.override(model=FunctionModel(_plain_reply_model("Hope it was fun."))),
            provenance_agent.override(model=FunctionModel(_provenance_pass)),
        ):
            await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message="I saw the film last night."),
                self.service,
                self.account,
            )

        async def judge(line, memories, paragraphs, statements):
            return PassageInferenceDecision(
                outcome="passages", work_id="pg11", book_version_id="pg11-v01b38ea4",
                confidence=0.98, authorization_basis="session_supported",
                supporting_statement_ids=(statements[0].statement_id,),
                supporting_evidence_ids=(QUOTE_ID,), passage_evidence_ids=(QUOTE_ID,),
            )

        with (
            patch("src.linger.orchestration.boundary.judge_spoiler_boundary", side_effect=judge),
            muse_chat_agent.override(model=FunctionModel(_muse_routes_then_relays_clarification())),
            provenance_agent.override(model=FunctionModel(_provenance_pass)),
        ):
            response = await chat_turn.run_chat_turn(
                ChatRequest(session_id=self.session_id, message=SECOND_LINE), self.service, self.account,
            )
        self.assertEqual("application_clarification", response.inspection.release.release_source)
        self.assertIn("latest chapter or scene", response.reply)
        self.assertEqual((), sessions.released_evidence_ids(self.session_id))
        self.assertIsNone(passage_grant())
        pending = sessions.pending_clarification(self.session_id)
        assert pending is not None
        self.assertEqual("progress_unverified", pending.reason_code)
