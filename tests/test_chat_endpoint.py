"""Tests for atomic chat history updates."""

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
    from apps.backend import main, sessions
    from apps.backend.schemas import ChatRequest
    from src.linger.agents.muse.models import MuseCandidate, NoMemoryCandidate
    from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding
    from src.linger.orchestration.reflection import (
        SAFE_DECLINE,
        ReflectionRelease,
        reflection_reply as run_reflection_gate,
    )
    from src.linger.services.memory import AccountContext, MemoryPolicyService


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    session_id = "endpoint-test"

    def setUp(self) -> None:
        self._memory_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._memory_directory.cleanup)
        self.memory_service = MemoryPolicyService(Path(self._memory_directory.name))
        self.memory_context = AccountContext("chat-endpoint-test")

    async def call_chat(self, request: ChatRequest):
        return await main.chat(request, self.memory_service, self.memory_context)

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

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
            with patch.object(main, "reflection_reply", gate):
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
        self.assertIn("agent_pipeline_failed", payload)
        self.assertIn("agent_pipeline_failed", logs)

    async def test_success_stores_only_released_turn(self) -> None:
        request = ChatRequest(session_id=self.session_id, message="Hello")
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Approved reply",
            release_source="muse_candidate",
            provenance_verdicts=("pass",),
        ))

        with patch.object(main, "reflection_reply", gate):
            response = await self.call_chat(request)

        self.assertEqual("Approved reply", response.reply)
        history = sessions.history(self.session_id)
        self.assertEqual("Hello", history[0].parts[0].content)
        self.assertEqual("Approved reply", history[1].parts[0].content)
        self.assertEqual("muse_candidate", response.inspection.release.release_source)
        self.assertEqual(("pass",), response.inspection.release.provenance_verdicts)
        review_context = gate.await_args.kwargs["review_context"]
        self.assertIn("policy_constraints", review_context)
        self.assertIn("cited_evidence", review_context)
        muse_payload = json.loads(gate.await_args.args[0])
        self.assertEqual("Hello", muse_payload["muse_turn"]["user_message"])
        self.assertIn("context_resolution", muse_payload)

    async def test_failure_stores_nothing(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="I am reading Animal Farm and I have finished Chapter 2.",
        )
        gate = AsyncMock(side_effect=RuntimeError("model failed"))

        with patch.object(main, "reflection_reply", gate):
            with self.assertRaises(HTTPException) as caught:
                await self.call_chat(request)

        self.assertEqual(502, caught.exception.status_code)
        self.assertTrue(caught.exception.__suppress_context__)
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

        with patch.object(main, "reflection_reply", gate):
            await self.call_chat(request)

        muse_payload = json.loads(gate.await_args.args[0])
        review_context = gate.await_args.kwargs["review_context"]
        self.assertEqual(3, muse_payload["muse_turn"]["policy"]["spoiler_ceiling"])
        self.assertEqual(muse_payload["supporting_evidence"], review_context["cited_evidence"])
        self.assertEqual(muse_payload["connection_proposal"], review_context["connection_proposal"])

    async def test_safe_decline_rolls_back_tentative_reading_state(self) -> None:
        request = ChatRequest(
            session_id=self.session_id,
            message="Why does the Caterpillar ask who Alice is?",
        )
        gate = AsyncMock(return_value=ReflectionRelease(
            reply="Safe decline",
            release_source="application_safe_decline",
            failure_stage="provenance_review",
        ))

        with patch.object(main, "reflection_reply", gate):
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
            )
        )

        with patch.object(main, "reflection_reply", gate):
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
                        quote=secret_quote,
                        explanation=secret_explanation,
                    ),
                ),
                response_decision="reject",
                capture_decision="no_candidate",
            )
        )
        release = await run_reflection_gate(
            "Hello",
            [],
            muse=muse,
            provenance=provenance,
        )
        gate = AsyncMock(return_value=release)

        with patch.object(main, "reflection_reply", gate):
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
                "provenance_verdicts",
                "finding_codes",
                "revision_count",
                "failure_stage",
                "capture",
            },
            set(response.inspection.release.model_dump()),
        )
        self.assertNotIn(secret_quote, payload)
        self.assertNotIn(secret_explanation, payload)
        self.assertNotIn('"critiques"', payload)
