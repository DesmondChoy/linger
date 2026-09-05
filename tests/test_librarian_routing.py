"""Tests for the Muse-facing `librarian_route` tool and its confidence union."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import logfire
from logfire.testing import TestExporter

from apps.backend import sessions
from apps.backend.config import Settings
from corpus_fixtures import fake_registration
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.agents.muse.tools import librarian_route
from src.linger.contracts.curation import CuratedMemory
from src.linger.contracts.librarian import (
    BoundaryCandidate,
    BoundarySupportLocation,
    BoundaryUncertain,
    ClarificationRequest,
    ExpectedAnswer,
    NoMatch,
    RoutedWork,
    effective_route_response,
)
from src.linger.corpus import registry
from src.linger.evaluation_transcript import active_evaluation_correlation_id
from src.linger.orchestration.boundary import infer_spoiler_boundary
from src.linger.orchestration.turn_context import (
    confirmed_reading,
    reset_active_memories,
    reset_reader_message,
    reset_session_id,
    set_active_memories,
    set_reader_message,
    set_session_id,
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


def _caterpillar_scene_memory() -> CuratedMemory:
    """A memory close enough to the actual chapter 5 text to score as evidence."""
    return CuratedMemory(
        memory_id="memory-alice",
        kind="original",
        text=(
            "The Caterpillar sitting on the mushroom asked Alice who she is, "
            "and I thought about keeping my temper too."
        ),
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
        self._session_token = None
        self._session_value = None

    async def asyncTearDown(self) -> None:
        if self._message_token is not None:
            reset_reader_message(self._message_token)
        if self._session_token is not None:
            reset_session_id(self._session_token)
        if self._session_value is not None:
            sessions.clear(self._session_value)
        reset_active_memories(self._token)
        self._settings_patch.stop()

    def _set_message(self, message: str) -> None:
        self._message_token = set_reader_message(message)

    def _set_session(self, session_id_value: str) -> None:
        self._session_token = set_session_id(session_id_value)
        self._session_value = session_id_value

    async def test_lone_generic_word_yields_no_match(self) -> None:
        self._set_message(
            "My afternoon in the garden while journaling about my grandmother "
            "was calming."
        )
        result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        self.assertTrue(result.request_id.startswith("routereq_"))

    async def test_common_words_yield_no_match_without_inference(self) -> None:
        for message in (
            "My friend Alice is stressed about work.",
            "What should I cook for dinner?",
            "A mouse ran through the kitchen.",
        ):
            with self.subTest(message=message):
                self._set_message(message)
                with patch(
                    "src.linger.orchestration.routing.infer_spoiler_boundary",
                    new=AsyncMock(),
                ) as infer:
                    result = await librarian_route()

                self.assertIsInstance(result, NoMatch)
                infer.assert_not_awaited()

    async def test_common_words_after_a_selection_still_route_only_to_that_selection(
        self,
    ) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        reset_active_memories(self._token)
        self._token = set_active_memories((_book_memory(),))
        candidate = BoundaryCandidate(
            kind="candidate", work_id="pg11", book_version_id="pg11-v01b38ea4",
            max_chapter_inclusive=5, confidence=0.9, authorization_basis="memory_supported",
            supporting_memory_ids=("memory-alice",),
            supporting_locations=(BoundarySupportLocation(
                evidence_id="pg11-v01b38ea4-ch05-ln0001-0002",
                chapter_number=5, location="Chapter 5",
            ),),
        )
        for message in (
            "My friend Alice is stressed about work.",
            "What should I cook for dinner?",
            "A mouse ran through the kitchen.",
        ):
            with self.subTest(message=message):
                self._set_message(message)
                with patch(
                    "src.linger.orchestration.routing.infer_spoiler_boundary",
                    new=AsyncMock(return_value=candidate),
                ) as infer:
                    result = await librarian_route()

                infer.assert_awaited_once()
                self.assertEqual("pg11", infer.await_args.kwargs["work_id"])
                self.assertIsInstance(result, RoutedWork)
                assert isinstance(result, RoutedWork)
                self.assertEqual("session_selection", result.selection_basis)

    async def test_confident_route_with_resolvable_boundary_is_routed(self) -> None:
        async def confident_judge(_line, memories, evidence, _statements):
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
        exporter = TestExporter()
        logfire.configure(
            send_to_logfire=False,
            console=False,
            inspect_arguments=False,
            additional_span_processors=[logfire.testing.SimpleSpanProcessor(exporter)],
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
        self.assertEqual("resolved_book_identity", result.selection_basis)
        route_span = next(
            span
            for span in exporter.exported_spans_as_dict()
            if span["name"] == "librarian.route"
        )
        self.assertEqual(
            "resolved_book_identity", route_span["attributes"]["routing.selection_basis"]
        )

    async def test_low_confidence_boundary_yields_clarification(self) -> None:
        async def uncertain_judge(_line, _memories, _evidence, _statements):
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

    async def test_active_selection_routes_an_indirect_follow_up_to_inference(self) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        self._set_message("Why did she do that?")
        uncertain = BoundaryUncertain(
            kind="uncertain", work_id="pg11", book_version_id="pg11-v01b38ea4",
            reason_code="insufficient_context",
            clarification_question="Which chapter have you finished?",
        )
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary",
            new=AsyncMock(return_value=uncertain),
        ) as infer:
            result = await librarian_route()

        infer.assert_awaited_once()
        self.assertEqual("Why did she do that?", infer.await_args.args[0])
        self.assertEqual("pg11", infer.await_args.kwargs["work_id"])
        self.assertEqual("pg11-v01b38ea4", infer.await_args.kwargs["book_version_id"])
        self.assertIsInstance(result, ClarificationRequest)
        assert isinstance(result, ClarificationRequest)
        self.assertEqual("insufficient_context", result.reason_code)
        selection = sessions.book_selection("route-session")
        assert selection is not None
        self.assertEqual("pg11", selection.book_id)

    async def test_active_selection_routes_with_session_selection_basis(self) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        reset_active_memories(self._token)
        self._token = set_active_memories((_book_memory(),))
        self._set_message("Why did she do that?")
        candidate = BoundaryCandidate(
            kind="candidate", work_id="pg11", book_version_id="pg11-v01b38ea4",
            max_chapter_inclusive=5, confidence=0.9, authorization_basis="memory_supported",
            supporting_memory_ids=("memory-alice",),
            supporting_locations=(BoundarySupportLocation(
                evidence_id="pg11-v01b38ea4-ch05-ln0001-0002",
                chapter_number=5, location="Chapter 5",
            ),),
        )
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary",
            new=AsyncMock(return_value=candidate),
        ):
            result = await librarian_route()

        self.assertIsInstance(result, RoutedWork)
        assert isinstance(result, RoutedWork)
        self.assertEqual("pg11", result.work_id)
        self.assertEqual("session_selection", result.selection_basis)
        self.assertEqual(5, result.max_chapter_inclusive)

    async def test_strong_cue_for_the_same_work_still_uses_the_active_selection(self) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        reset_active_memories(self._token)
        self._token = set_active_memories((_book_memory(),))
        self._set_message("I keep thinking about the White Rabbit today.")
        candidate = BoundaryCandidate(
            kind="candidate", work_id="pg11", book_version_id="pg11-v01b38ea4",
            max_chapter_inclusive=3, confidence=0.9, authorization_basis="memory_supported",
            supporting_memory_ids=("memory-alice",),
            supporting_locations=(BoundarySupportLocation(
                evidence_id="pg11-v01b38ea4-ch03-ln0001-0002",
                chapter_number=3, location="Chapter 3",
            ),),
        )
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary",
            new=AsyncMock(return_value=candidate),
        ):
            result = await librarian_route()

        self.assertIsInstance(result, RoutedWork)
        assert isinstance(result, RoutedWork)
        self.assertEqual("pg11", result.work_id)
        self.assertEqual("session_selection", result.selection_basis)

    async def test_unrelated_turn_after_selection_reaches_inference_and_is_declined(self) -> None:
        async def declining_judge(_line, _memories, _evidence, _statements):
            return BoundaryInferenceDecision(
                outcome="uncertain", confidence=0.1, reason_code="insufficient_context",
            )

        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        reset_active_memories(self._token)
        self._token = set_active_memories((_caterpillar_scene_memory(),))
        self._set_message("Help me repair my bicycle.")
        # Inference must run for the session fallback; the boundary path declines
        # before or at the judge because the unrelated line retrieves no evidence.
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary",
            new=AsyncMock(wraps=infer_spoiler_boundary),
        ) as infer, patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=declining_judge,
        ):
            result = await librarian_route()

        self.assertEqual(1, infer.await_count)
        self.assertIsInstance(result, ClarificationRequest)
        self.assertIsNone(sessions.reading_candidate("route-session"))
        self.assertIsNone(confirmed_reading())

    async def test_strong_cue_for_another_work_beats_the_active_selection(self) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        self._set_message("I keep thinking about Quendra Vale today.")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            second = fake_registration(root, work_id="second", catalog={
                "title": "A Different Garden",
                "chapters": [{"chapter_number": 1, "characters": ["Quendra Vale"]}],
            })
            corpora = {"pg11": registry.CORPORA["pg11"], "second": second}
            settings = Settings(
                _env_file=None,
                linger_model="google:gemini-2.5-flash",
                google_api_key="test-key",
                allowed_book_version_ids=(
                    registry.CORPORA["pg11"].book.book_version_id,
                    second.book.book_version_id,
                ),
            )
            with patch("src.linger.corpus.registry.CORPORA", corpora), \
                 patch("src.linger.orchestration.routing.get_settings", return_value=settings), \
                 patch(
                     "src.linger.orchestration.routing.infer_spoiler_boundary",
                     new=AsyncMock(),
                 ) as infer:
                result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        infer.assert_not_awaited()

    async def test_selection_for_a_disallowed_revision_does_not_route(self) -> None:
        sessions.set_book_selection(
            "route-session",
            sessions.BookSelection(book_id="pg11", book_title="Alice's Adventures in Wonderland"),
        )
        self._set_session("route-session")
        self._set_message("Why did she do that?")
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
            allowed_book_version_ids=("other-revision",),
        )
        with patch("src.linger.orchestration.routing.get_settings", return_value=settings), patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(),
        ) as infer:
            result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        infer.assert_not_awaited()

    async def test_no_selection_and_no_cue_stays_no_match(self) -> None:
        self._set_message("Why did she do that?")
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(),
        ) as infer:
            result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        infer.assert_not_awaited()

    async def test_bare_adaptation_question_without_a_selection_is_no_match(self) -> None:
        self._set_message("Why is time stuck at the Mad Tea Party?")
        with patch(
            "src.linger.orchestration.routing.infer_spoiler_boundary", new=AsyncMock(),
        ) as infer:
            result = await librarian_route()

        self.assertIsInstance(result, NoMatch)
        infer.assert_not_awaited()

    async def test_quotation_style_question_naming_the_book_clarifies_progress(self) -> None:
        async def line_only_judge(_line, _memories, evidence, _statements):
            self.assertTrue(evidence, "retrieval must surface evidence for the judge to run")
            return BoundaryInferenceDecision(
                outcome="candidate",
                work_id="pg11",
                book_version_id="pg11-v01b38ea4",
                chapter_number=evidence[0].chapter_number,
                confidence=0.99,
                authorization_basis="line_only",
                supporting_evidence_ids=(evidence[0].evidence_id,),
            )

        self._set_message(
            "Can we talk about the Mad Tea Party in Alice in Wonderland today?"
        )
        with patch(
            "src.linger.orchestration.boundary.judge_spoiler_boundary",
            side_effect=line_only_judge,
        ):
            result = await librarian_route()

        self.assertIsInstance(result, ClarificationRequest)
        assert isinstance(result, ClarificationRequest)
        self.assertEqual("progress_unverified", result.reason_code)
        self.assertIsNone(confirmed_reading())


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
            selection_basis="resolved_book_identity",
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
