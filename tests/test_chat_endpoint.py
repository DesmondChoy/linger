"""Tests for atomic chat history updates."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import logfire
from fastapi import HTTPException
from fastapi.testclient import TestClient
from logfire.testing import TestExporter

from apps.backend.config import get_settings

get_settings.cache_clear()
with patch.dict(
    os.environ,
    {
        "LINGER_MODEL": "google:gemini-2.5-flash",
        "GOOGLE_API_KEY": "test-key",
    },
):
    from apps.backend import chat_turn, main, sessions
    from apps.backend.schemas import ChatRequest
    from src.linger.agents.muse.models import MuseCandidate, NoMemoryCandidate
    from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
    from src.linger.orchestration.reflection import (
        SAFE_DECLINE,
        ReflectionRelease,
        reflection_reply as run_reflection_gate,
    )
    from src.linger.orchestration.inspection_context import ConnectionRunInspection
    from src.linger.services.memory import AccountContext, MemoryPolicyService
    from src.linger.contracts.emotional import EmotionalBoundaryAssessment


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    session_id = "endpoint-test"

    def setUp(self) -> None:
        self._memory_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._memory_directory.cleanup)
        self.memory_service = MemoryPolicyService(Path(self._memory_directory.name))
        self.memory_context = AccountContext("chat-endpoint-test")
        self._boundary_patcher = patch.object(
            chat_turn,
            "assess_emotional_boundary",
            AsyncMock(
                return_value=EmotionalBoundaryAssessment(
                    decision="continue_reflection"
                )
            ),
        )
        self._boundary_patcher.start()
        self.addCleanup(self._boundary_patcher.stop)

    async def call_chat(self, request: ChatRequest):
        return await main.chat(request, self.memory_service, self.memory_context)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    def test_direct_memory_controls_are_not_exposed(self) -> None:
        with TestClient(main.app) as client:
            requests = (
                client.get("/api/memories"),
                client.put("/api/memory-capture-preference", json={"enabled": True}),
                client.post("/api/memories", json={"text": "Save this"}),
                client.put("/api/memories/mem-1", json={"text": "Correct this"}),
                client.delete("/api/memories/mem-1"),
            )

        self.assertTrue(all(response.status_code == 404 for response in requests))

    def test_http_and_file_telemetry_exclude_request_content(self) -> None:
        exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[
                logfire.testing.SimpleSpanProcessor(exporter)
            ],
        )
        session_marker = "qazws-private-session-qazws"
        turn_marker = "edcrf-private-turn-edcrf"
        message_marker = "tgbnh-private-message-tgbnh"
        query_marker = "yhnuj-private-query-yhnuj"
        path_marker = "ikmol-private-path-ikmol"
        exception_marker = "olpaz-private-exception-olpaz"
        gate = AsyncMock(side_effect=RuntimeError(exception_marker))

        with self.assertLogs("linger.backend", level="ERROR") as captured:
            with patch.object(chat_turn, "reflection_reply", gate):
                response = TestClient(main.app).post(
                    f"/api/chat?debug={query_marker}",
                    json={
                        "session_id": session_marker,
                        "turn_id": turn_marker,
                        "message": message_marker,
                    },
                )
        TestClient(main.app).delete(f"/api/sessions/{path_marker}")

        self.assertEqual(502, response.status_code)
        payload = json.dumps(exporter.exported_spans_as_dict(), default=str)
        logs = "\n".join(captured.output)
        for marker in (
            session_marker,
            turn_marker,
            message_marker,
            query_marker,
            path_marker,
            exception_marker,
        ):
            self.assertNotIn(marker, payload)
            self.assertNotIn(marker, logs)
        self.assertIn("chat_turn_failed", payload)
        self.assertIn("chat_turn_failed", logs)

    def test_failure_returns_only_safe_trace_correlation(self) -> None:
        exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[
                logfire.testing.SimpleSpanProcessor(exporter)
            ],
        )
        gate = AsyncMock(side_effect=RuntimeError("private provider failure"))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = TestClient(main.app).post(
                "/api/chat",
                json={
                    "session_id": self.session_id,
                    "turn_id": "failed-turn",
                    "message": "Private reader message",
                },
            )

        self.assertEqual(502, response.status_code)
        payload = response.json()["detail"]
        self.assertEqual("The model call failed. Try again.", payload["message"])
        self.assertRegex(payload["trace"]["trace_id"], r"^[0-9a-f]{32}$")
        self.assertNotIn("Private reader message", response.text)
        self.assertNotIn("private provider failure", response.text)
        request_span = next(
            span
            for span in exporter.exported_spans_as_dict()
            if span["name"] == "chat.request"
        )
        turn_span = next(
            span
            for span in exporter.exported_spans_as_dict()
            if span["name"] == "chat.turn"
        )
        attributes = request_span["attributes"]
        self.assertEqual("/api/chat", attributes["http.route"])
        self.assertEqual(502, attributes["http.response.status_code"])
        self.assertEqual("failed", attributes["request.outcome"])
        self.assertEqual(request_span["context"]["trace_id"], turn_span["context"]["trace_id"])
        self.assertEqual(request_span["context"]["span_id"], turn_span["parent"]["span_id"])
        self.assertEqual("chat_turn", turn_span["attributes"]["failure.stage"])

    async def test_application_failure_uses_a_transport_independent_error(self) -> None:
        gate = AsyncMock(side_effect=RuntimeError("private provider failure"))
        request = ChatRequest(session_id=self.session_id, message="Private reader message")

        with patch.object(chat_turn, "reflection_reply", gate):
            with self.assertRaises(chat_turn.ChatTurnError) as caught:
                await chat_turn.run_chat_turn(
                    request,
                    self.memory_service,
                    self.memory_context,
                )

        self.assertRegex(caught.exception.trace.trace_id, r"^[0-9a-f]{32}$")

    async def test_success_stores_only_released_turn(self) -> None:
        request = ChatRequest(session_id=self.session_id, message="Hello")
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(request)

        self.assertEqual("Approved reply", response.reply)
        self.assertRegex(response.trace.trace_id, r"^[0-9a-f]{32}$")
        history = sessions.history(self.session_id)
        self.assertEqual("Hello", history[0].parts[0].content)
        self.assertEqual("Approved reply", history[1].parts[0].content)
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(("pass",), response.inspection.release.provenance_verdicts)
        review_context = gate.await_args.kwargs["review_context"]
        self.assertIn("policy_constraints", review_context)
        muse_payload = json.loads(gate.await_args.args[0])
        self.assertEqual(
            {"mode", "muse_turn", "context_resolution", "prior_evidence"},
            set(muse_payload),
        )
        self.assertEqual("draft", muse_payload["mode"])
        self.assertEqual("Hello", muse_payload["muse_turn"]["user_message"])
        self.assertFalse(muse_payload["muse_turn"]["policy"]["allow_connection"])
        self.assertIn("context_resolution", muse_payload)
        serendipity_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Serendipity"
        )
        librarian_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Librarian"
        )
        self.assertEqual("skipped", serendipity_trace["status"])
        self.assertIn("did not call", serendipity_trace["detail"])
        self.assertEqual("skipped", librarian_trace["status"])

    async def test_web_grant_allows_bookless_connection_discovery(self) -> None:
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "web_reach_permitted", return_value=True):
            with patch.object(chat_turn, "reflection_reply", gate):
                response = await self.call_chat(
                    ChatRequest(session_id=self.session_id, message="Recommend an essay")
                )

        policy = response.inspection.muse_turn["policy"]
        self.assertTrue(policy["allow_connection"])
        self.assertFalse(policy["allow_retrieval"])
        self.assertIsNone(response.inspection.muse_turn["reading_context"])

    async def test_direct_grounding_calls_reach_the_inspector(self) -> None:
        request = ChatRequest(session_id=self.session_id, message="What happens in chapter 2?")
        grounding_call = {
            "request": {"query": "chapter 2", "work_id": "pg11"},
            "outcome": "success",
            "response": {"kind": "result", "outcome": "evidence_found"},
        }
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Grounded reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
            librarian_grounding_calls=(grounding_call,),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(request)

        self.assertEqual([grounding_call], response.inspection.librarian_grounding)
        librarian_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Librarian"
        )
        self.assertEqual("complete", librarian_trace["status"])
        self.assertIn("Librarian directly", librarian_trace["detail"])

    async def test_direct_grounding_failure_is_not_reported_complete(self) -> None:
        grounding_call = {
            "request": {"query": "chapter 2", "work_id": "pg11"},
            "outcome": "success",
            "response": {
                "kind": "failure",
                "error_code": "retrieval_unavailable",
                "retryable": True,
            },
        }
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="I could not search the book safely just now.",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
            librarian_grounding_calls=(grounding_call,),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Search chapter 2")
            )

        librarian_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Librarian"
        )
        self.assertEqual("failed", librarian_trace["status"])
        self.assertIn("failed", librarian_trace["detail"])

    async def test_failed_connection_search_is_not_reported_complete(self) -> None:
        run = ConnectionRunInspection(
            status="decline",
            reason="retrieval_unavailable",
            book_search_outcomes=("retrieval_unavailable",),
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="I could not find a safe connection just now.",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate), patch.object(
            chat_turn,
            "connection_inspections",
            return_value=(run,),
        ):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Find a connection")
            )

        librarian_trace = next(
            trace
            for trace in response.inspection.traces
            if trace["agent"] == "Librarian"
        )
        self.assertEqual("failed", librarian_trace["status"])
        self.assertIn("failed", librarian_trace["detail"])

    async def test_declined_connection_inspection_is_fixed_metadata_only(self) -> None:
        private_marker = "PRIVATE_DECLINED_CONNECTION_CONTENT_6a4d"
        run = ConnectionRunInspection(
            status="decline",
            reason="unsafe_evidence",
            book_search_outcomes=("no_evidence",),
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved direct reflection",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            with patch.object(chat_turn, "connection_inspections", return_value=(run,)):
                response = await self.call_chat(
                    ChatRequest(session_id=self.session_id, message="Hello")
                )

        self.assertEqual(
            {
                "reason": "unsafe_evidence",
                "failure_code": None,
            },
            response.inspection.connection_decline.model_dump(),
        )
        inspection_fields = response.inspection.model_dump()
        for removed_field in (
            "connection_brief",
            "connection_discovery_input",
            "serendipity_searches",
            "librarian_request",
            "evidence_bundle",
            "connection_proposal",
        ):
            self.assertNotIn(removed_field, inspection_fields)
        self.assertNotIn(private_marker, response.model_dump_json())

    async def test_safe_decline_suppresses_nested_inspection_content(self) -> None:
        private_marker = "PRIVATE_WITHHELD_RELEASE_CONTENT_91e2"
        run = ConnectionRunInspection(
            status="proposal",
            reason=None,
            book_search_outcomes=("evidence_found",),
        )
        grounding_call = {
            "request": {"query": private_marker},
            "outcome": "success",
            "response": {"excerpt": private_marker},
        }
        gate = AsyncMock(return_value=ReflectionRelease(
            reply=SAFE_DECLINE,
            release_source="application_safe_decline",
            provenance_verdicts=("pass",),
            failure_stage="deterministic_validation",
            failure_type="validation",
            failure_retryable=False,
            librarian_grounding_calls=(grounding_call,),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            with patch.object(chat_turn, "connection_inspections", return_value=(run,)):
                response = await self.call_chat(
                    ChatRequest(session_id=self.session_id, message="Hello")
                )

        inspection_fields = response.inspection.model_dump()
        for removed_field in (
            "connection_brief",
            "connection_discovery_input",
            "serendipity_searches",
            "librarian_request",
            "evidence_bundle",
            "connection_proposal",
        ):
            self.assertNotIn(removed_field, inspection_fields)
        self.assertEqual([], response.inspection.librarian_grounding)
        self.assertNotIn(private_marker, response.model_dump_json())

    async def test_failure_stores_nothing(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I am reading Animal Farm and I have finished Chapter 2.",
        )
        gate = AsyncMock(side_effect=RuntimeError("model failed"))

        with patch.object(chat_turn, "reflection_reply", gate):
            with self.assertRaises(HTTPException) as caught:
                await self.call_chat(request)

        self.assertEqual(502, caught.exception.status_code)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual([], sessions.history(self.session_id))
        self.assertIsNone(sessions.book_selection(self.session_id))
        self.assertIsNone(sessions.reading_candidate(self.session_id))

    async def test_cancellation_rolls_back_tentative_reading_state(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I am reading Animal Farm and I have finished Chapter 2.",
        )
        entered = asyncio.Event()
        blocker = asyncio.Event()

        async def cancelled_gate(*args, **kwargs):
            entered.set()
            await blocker.wait()

        with patch.object(chat_turn, "reflection_reply", cancelled_gate):
            task = asyncio.create_task(self.call_chat(request))
            await asyncio.wait_for(entered.wait(), timeout=1)
            # resolve_reading_context already confirmed the chapter synchronously.
            self.assertIsNotNone(sessions.book_selection(self.session_id))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual([], sessions.history(self.session_id))
        self.assertIsNone(sessions.book_selection(self.session_id))
        self.assertIsNone(sessions.reading_candidate(self.session_id))

    async def test_grounded_turn_shares_the_same_context_with_muse_and_provenance(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message=(
                "I am reading Animal Farm and I have finished Chapter 3. "
                "Why does the milk connect to power and equality?"
            ),
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved grounded reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            await self.call_chat(request)

        muse_payload = json.loads(gate.await_args.args[0])
        review_context = gate.await_args.kwargs["review_context"]
        self.assertEqual(3, muse_payload["muse_turn"]["policy"]["spoiler_ceiling"])
        self.assertEqual(
            muse_payload["muse_turn"]["reading_context"],
            review_context["reading_context"],
        )
        self.assertEqual(
            muse_payload["muse_turn"]["policy"],
            review_context["policy_constraints"],
        )

    async def test_released_citations_reach_inspection(self) -> None:
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved grounded reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
            evidence_ids=("ev-1", "ev-2"),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        self.assertEqual(
            ("ev-1", "ev-2"), response.inspection.release.released_evidence_ids
        )

    async def test_agent_call_failure_is_distinguishable_from_a_verdict(self) -> None:
        """A provider fault and a semantic rejection both decline; only one is
        retryable, and inspection must say which."""
        gate = AsyncMock(return_value=ReflectionRelease(
            reply=SAFE_DECLINE,
            release_source="application_safe_decline",
            failure_stage="provenance_review",
            failure_type="model",
            failure_retryable=True,
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        release = response.inspection.release
        self.assertEqual("provenance_review", release.failure_stage)
        self.assertEqual("model", release.failure_type)
        self.assertTrue(release.failure_retryable)

    async def test_a_clean_release_carries_no_failure_classification(self) -> None:
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved.",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        release = response.inspection.release
        self.assertIsNone(release.failure_stage)
        self.assertIsNone(release.failure_type)
        self.assertIsNone(release.failure_retryable)

    async def test_rejected_draft_citations_never_reach_inspection(self) -> None:
        """A blocked candidate still declares evidence; it was never released."""
        gate = AsyncMock(return_value=ReflectionRelease(
            reply=SAFE_DECLINE,
            release_source="application_safe_decline",
            provenance_verdicts=("reject",),
            finding_codes=("spoiler",),
            evidence_ids=("ev-rejected",),
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        self.assertEqual((), response.inspection.release.released_evidence_ids)
        self.assertNotIn("ev-rejected", response.model_dump_json())

    async def test_safe_decline_rolls_back_tentative_reading_state(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="Why does the Caterpillar ask who Alice is?",
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Safe decline",
            release_source="application_safe_decline",
            failure_stage="provenance_review",
            failure_type="model",
            failure_retryable=True,
        ))

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(request)

        self.assertEqual("Safe decline", response.reply)
        self.assertIsNone(sessions.reading_candidate(self.session_id))
        self.assertEqual(
            "application_safe_decline", response.inspection.release.release_source
        )

    async def test_deterministic_validation_failure_is_serialized(self) -> None:
        gate = AsyncMock(
            return_value=ReflectionRelease(
                reply=SAFE_DECLINE,
                release_source="application_safe_decline",
                provenance_verdicts=("pass",),
                failure_stage="deterministic_validation",
                failure_type="validation",
                failure_retryable=False,
            )
        )

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        self.assertEqual(SAFE_DECLINE, response.reply)
        self.assertEqual(
            "deterministic_validation", response.inspection.release.failure_stage
        )
        self.assertEqual("not_run", response.inspection.traces[-1]["status"])

    async def test_rejected_critique_never_reaches_serialized_response(self) -> None:
        secret_quote = "PRIVATE_REJECTED_QUOTE_7f68b6"
        secret_explanation = "PRIVATE_REVIEW_EXPLANATION_34ab91"
        muse = AsyncMock()
        muse.run.return_value = SimpleNamespace(
            output=MuseCandidate(
                reply="Unsafe draft",
                memory=NoMemoryCandidate(
                    kind="no_memory_candidate",
                    reason_code="transient_or_low_signal",
                ),
            ),
            new_messages=lambda: [],
        )
        provenance = AsyncMock()
        provenance.run.return_value = SimpleNamespace(
            output=ProvenanceReview(
                findings=(
                    RiskFinding(
                        code="unsupported_claim",
                        applies_to="response",
                        location={
                            "kind": "structural",
                            "source_field": "candidate.response",
                            "path": "",
                        },
                        explanation=secret_explanation,
                    ),
                ),
                response_decision="reject",
                emotional_boundary_decision="not_required",
                capture_decision="no_candidate",
            )
        )
        _, muse_input, review_context = chat_turn.prepare_reflection_turn(
            ChatRequest(session_id=self.session_id, message="Hello"),
            allow_memory_capture=False,
        )
        release = await run_reflection_gate(
            muse_input,
            [],
            muse=muse,
            provenance=provenance,
            review_context=review_context,
            capture_source_text="Hello",
        )
        gate = AsyncMock(return_value=release)

        with patch.object(chat_turn, "reflection_reply", gate):
            response = await self.call_chat(
                ChatRequest(session_id=self.session_id, message="Hello")
            )

        payload = response.model_dump_json()
        self.assertEqual(SAFE_DECLINE, response.reply)
        self.assertEqual(
            ("unsupported_claim",), response.inspection.release.finding_codes
        )
        self.assertEqual(
            {
                "release_source",
                "boundary_origin",
                "provenance_verdicts",
                "finding_codes",
                "released_evidence_ids",
                "revision_count",
                "failure_stage",
                "failure_type",
                "failure_retryable",
                "capture",
            },
            set(response.inspection.release.model_dump()),
        )
        # A safe decline released no reply, so it cites nothing.
        self.assertEqual((), response.inspection.release.released_evidence_ids)
        self.assertNotIn(secret_quote, payload)
        self.assertNotIn(secret_explanation, payload)
        self.assertNotIn('"critiques"', payload)
