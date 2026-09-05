"""Tests for the Muse-facing `librarian_route` tool and its confidence union."""

import unittest
from unittest.mock import patch

from apps.backend.config import Settings
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.agents.muse.tools import librarian_route
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.librarian import (
    BoundaryUncertain,
    ClarificationRequest,
    ExpectedAnswer,
    NoMatch,
    RoutedWork,
    effective_route_response,
)
from src.linger.evaluation_transcript import active_evaluation_correlation_id
from src.linger.orchestration.turn_context import (
    reset_active_memories,
    reset_reader_message,
    set_active_memories,
    set_reader_message,
)


def _book_memory() -> CuratedMemory:
    return CuratedMemory(
        memory_id="memory-alice",
        kind="original",
        text="Alice and the Caterpillar made me think about identity.",
        source_memory_ids=("memory-alice",),
        evidence_ids=(),
        created_at="2026-08-28T00:00:00+00:00",
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        linger_model="google:gemini-2.5-flash",
        google_api_key="test-key",
        allowed_book_version_ids=("pg11-v01b38ea4",),
    )


class LibrarianRouteToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._settings_patch = patch(
            "src.linger.orchestration.routing.get_settings", return_value=_settings()
        )
        self._settings_patch.start()
        self._token = set_active_memories(())
        self._message_token = None

    async def asyncTearDown(self) -> None:
        if self._message_token is not None:
            reset_reader_message(self._message_token)
        reset_active_memories(self._token)
        self._settings_patch.stop()

    def _set_message(self, message: str) -> None:
        self._message_token = set_reader_message(message)

    async def test_lone_generic_word_yields_no_match(self) -> None:
        self._set_message(
            "My afternoon in the garden while journaling about my grandmother "
            "was calming."
        )
        result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        self.assertTrue(result.request_id.startswith("routereq_"))

    async def test_confident_route_with_resolvable_boundary_is_routed(self) -> None:
        async def confident_judge(_line, memories, evidence):
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_number=max(record.chapter_number for record in evidence),
                confidence=0.95,
                authorization_basis="memory_supported",
                supporting_memory_ids=[memory.memory_id for memory in memories],
                supporting_evidence_ids=[record.evidence_id for record in evidence],
            )

        # A ceiling needs an account-scoped memory backing the routed work.
        reset_active_memories(self._token)
        self._token = set_active_memories((_book_memory(),))
        self._set_message(
            "Can we talk about Alice's Adventures in Wonderland? I just "
            "finished the caterpillar's advice."
        )
        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=confident_judge,
        ):
            result = await librarian_route()

        self.assertIsInstance(result, RoutedWork)
        assert isinstance(result, RoutedWork)
        self.assertTrue(result.request_id.startswith("routereq_"))
        self.assertEqual("pg11", result.work_id)
        self.assertEqual(1.0, result.routing_confidence)
        self.assertGreaterEqual(result.boundary_confidence, 0.75)

    async def test_low_confidence_boundary_yields_clarification(self) -> None:
        async def uncertain_judge(_line, _memories, _evidence):
            return BoundaryInferenceDecision(
                outcome="uncertain",
                confidence=0.2,
                reason_code="insufficient_context",
            )

        self._set_message("Can we talk about Alice's Adventures in Wonderland today?")
        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=uncertain_judge,
        ):
            result = await librarian_route()

        self.assertIsInstance(result, ClarificationRequest)

    async def test_route_request_id_scopes_boundary_evaluation_correlation(self) -> None:
        seen_correlation_ids: list[str | None] = []

        async def uncertain_boundary(*_args, **_kwargs):
            seen_correlation_ids.append(active_evaluation_correlation_id())
            return BoundaryUncertain(
                kind="uncertain",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                reason_code="insufficient_context",
                clarification_question="How far have you read?",
            )

        self._set_message("Can we talk about Alice's Adventures in Wonderland?")
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary",
            side_effect=uncertain_boundary,
        ):
            result = await librarian_route()

        self.assertEqual([result.request_id], seen_correlation_ids)
        self.assertIsNone(active_evaluation_correlation_id())


class EffectiveRouteResponseTests(unittest.TestCase):
    @staticmethod
    def routed(request_id: str, chapter: int) -> RoutedWork:
        return RoutedWork(
            kind="routed",
            request_id=request_id,
            work_id="pg11",
            book_version_id="pg11-v01b38ea4",
            title="Alice's Adventures in Wonderland",
            routing_confidence=1.0,
            max_chapter_inclusive=chapter,
            boundary_confidence=0.9,
        )

    @staticmethod
    def clarification(request_id: str, question: str) -> ClarificationRequest:
        return ClarificationRequest(
            kind="clarification",
            request_id=request_id,
            clarification_id=f"clarify-{request_id}",
            reason_code="insufficient_context",
            question=question,
            expected_answer=ExpectedAnswer(type="free_text"),
        )

    def test_first_clarification_wins_even_after_a_routed_result(self) -> None:
        first_routed = self.routed("routereq-routed", 5)
        first_clarification = self.clarification(
            "routereq-clarify-1", "How far have you read?"
        )
        second_clarification = self.clarification(
            "routereq-clarify-2", "Which chapter did you finish?"
        )

        self.assertIs(
            first_clarification,
            effective_route_response(
                (first_routed, first_clarification, second_clarification)
            ),
        )

    def test_first_routed_result_wins_when_no_clarification_exists(self) -> None:
        no_match = NoMatch(kind="no_match", request_id="routereq-none")
        first_routed = self.routed("routereq-routed-1", 5)
        second_routed = self.routed("routereq-routed-2", 7)

        self.assertIs(
            first_routed,
            effective_route_response((no_match, first_routed, second_routed)),
        )

    def test_first_no_match_or_none_is_the_fallback(self) -> None:
        first = NoMatch(kind="no_match", request_id="routereq-none-1")
        second = NoMatch(kind="no_match", request_id="routereq-none-2")

        self.assertIs(first, effective_route_response((first, second)))
        self.assertIsNone(effective_route_response(()))


if __name__ == "__main__":
    unittest.main()
