"""Tests for the additive Layer 2 grounding module and its settings field."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.backend.config import Settings, get_settings
from apps.backend.contracts import EvidenceBundle, EvidenceItem
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    ClarificationRequest,
    RetrievalFailure,
    RetrievalResult,
    SearchedScope,
)
from src.linger.contracts.reading import ReadingBoundary
from src.linger.contracts.turn import ConfirmedReading
from src.linger.orchestration.grounding import BookVersionOutOfScope, build_request, grounding_evidence
from src.linger.orchestration.turn_context import (
    confirmed_reading,
    reset_confirmed_reading,
    set_confirmed_reading,
)


class SettingsGroundingFieldTests(unittest.TestCase):
    def test_default_allowed_book_version_ids(self) -> None:
        settings = Settings(_env_file=None)
        self.assertEqual(("pg11-v01b38ea4",), settings.allowed_book_version_ids)

    def test_allowed_book_version_ids_overridable(self) -> None:
        settings = Settings(_env_file=None, allowed_book_version_ids=("x",))
        self.assertEqual(("x",), settings.allowed_book_version_ids)


class ConfirmedReadingContextVarTests(unittest.TestCase):
    def test_unset_reads_none(self) -> None:
        self.assertIsNone(confirmed_reading())

    def test_round_trip(self) -> None:
        reading = ConfirmedReading(work_id="pg11", chapter_max=3)
        token = set_confirmed_reading(reading)
        try:
            self.assertEqual(reading, confirmed_reading())
        finally:
            reset_confirmed_reading(token)
        self.assertIsNone(confirmed_reading())

    def test_reset_restores_prior_value(self) -> None:
        outer = ConfirmedReading(work_id="pg11", chapter_max=3)
        outer_token = set_confirmed_reading(outer)
        try:
            inner = ConfirmedReading(work_id="animal-farm", chapter_max=1)
            inner_token = set_confirmed_reading(inner)
            reset_confirmed_reading(inner_token)
            self.assertEqual(outer, confirmed_reading())
        finally:
            reset_confirmed_reading(outer_token)


class ConcurrentTurnIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_gathered_tasks_do_not_see_each_others_confirmed_reading(self) -> None:
        results: dict[str, ConfirmedReading | None] = {}

        async def run_turn(name: str, work_id: str) -> None:
            reading = ConfirmedReading(work_id=work_id, chapter_max=2)
            token = set_confirmed_reading(reading)
            try:
                await asyncio.sleep(0)
                results[name] = confirmed_reading()
            finally:
                reset_confirmed_reading(token)

        await asyncio.gather(
            run_turn("a", "pg11"),
            run_turn("b", "animal-farm"),
        )

        self.assertEqual("pg11", results["a"].work_id)
        self.assertEqual("animal-farm", results["b"].work_id)


WORK_ID = "pg11"
VALID_VERSION = get_settings().allowed_book_version_ids[0]
SOURCE_SHA256 = "01b38ea4c710a84bc18d0bd41271a5a1a92b94e97b2812f4dece97d4a694725e"


def evidence_item(evidence_id: str, chapter: int, excerpt: str = "text") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        work_id=WORK_ID,
        book_version_id=VALID_VERSION,
        chapter_id=f"{VALID_VERSION}-ch{chapter:02d}",
        source_title="Alice's Adventures in Wonderland",
        location=f"Chapter {chapter}",
        chapter=chapter,
        source_sha256=SOURCE_SHA256,
        source_lines=(chapter, chapter),
        excerpt=excerpt,
        relevance=0.9,
    )


class GroundingEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._token = None

    def _confirm(self, work_id: str = WORK_ID, chapter_max: int = 5) -> None:
        self._token = set_confirmed_reading(ConfirmedReading(work_id=work_id, chapter_max=chapter_max))

    def _judge(
        self,
        strength: str,
        evidence_ids: tuple[str, ...],
        *,
        reason: str = "Judged from the complete evidence set.",
    ) -> AsyncMock:
        limitations = ("The evidence only partially answers the query.",) if strength == "weak" else ()
        return AsyncMock(
            return_value=EvidenceStrengthDecision(
                evidence_strength=strength,
                strength_reason=reason,
                relevant_evidence_ids=evidence_ids,
                limitations=limitations,
            )
        )

    def tearDown(self) -> None:
        if self._token is not None:
            reset_confirmed_reading(self._token)

    async def test_out_of_scope_book_version_raises_and_never_dispatches(self) -> None:
        self._confirm()
        librarian = MagicMock()
        request = build_request("query", WORK_ID, "not-an-allowed-version", ReadingBoundary(chapter_number=2, chapter_state="completed"))

        with self.assertRaises(BookVersionOutOfScope):
            await grounding_evidence(request, librarian=librarian)

        librarian.retrieve.assert_not_called()

    async def test_no_reading_boundary_returns_clarification_without_dispatch(self) -> None:
        self._confirm()
        librarian = MagicMock()
        request = build_request("query", WORK_ID, VALID_VERSION, None)

        response = await grounding_evidence(request, librarian=librarian)

        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual("current_chapter_state_ambiguous", response.reason_code)
        librarian.retrieve.assert_not_called()

    async def test_no_confirmed_reading_returns_clarification_without_dispatch(self) -> None:
        librarian = MagicMock()
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=2, chapter_state="completed"))

        judge = self._judge("weak", ("e1",))
        response = await grounding_evidence(
            request, librarian=librarian, strength_judge=judge
        )

        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual("reading_boundary_unconfirmed", response.reason_code)
        librarian.retrieve.assert_not_called()
        judge.assert_not_awaited()

    async def test_work_id_mismatch_returns_clarification_without_dispatch(self) -> None:
        self._confirm(work_id="animal-farm")
        librarian = MagicMock()
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=2, chapter_state="completed"))

        response = await grounding_evidence(request, librarian=librarian)

        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual("work_not_confirmed", response.reason_code)
        librarian.retrieve.assert_not_called()

    async def test_started_and_completed_ceilings(self) -> None:
        cases = [
            ("started", 5, 4),
            ("completed", 5, 5),
        ]
        for chapter_state, chapter_number, expected_ceiling in cases:
            with self.subTest(chapter_state=chapter_state):
                self._confirm(chapter_max=5)
                librarian = MagicMock()
                librarian.retrieve.return_value = EvidenceBundle(items=[], retrieval_note="")
                request = build_request(
                    "query", WORK_ID, VALID_VERSION,
                    ReadingBoundary(chapter_number=chapter_number, chapter_state=chapter_state),
                )

                await grounding_evidence(request, librarian=librarian)

                called_request = librarian.retrieve.call_args.args[0]
                self.assertEqual(expected_ceiling, called_request.book_scopes[0].chapter_max)
                reset_confirmed_reading(self._token)
                self._token = None

    async def test_clamp_muse_cannot_widen_past_confirmed_ceiling(self) -> None:
        self._confirm(chapter_max=3)
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(items=[], retrieval_note="")
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=9, chapter_state="completed"))

        await grounding_evidence(request, librarian=librarian)

        called_request = librarian.retrieve.call_args.args[0]
        self.assertEqual(3, called_request.book_scopes[0].chapter_max)

    async def test_muse_may_narrow_below_confirmed_ceiling(self) -> None:
        self._confirm(chapter_max=7)
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(items=[], retrieval_note="")
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=2, chapter_state="completed"))

        await grounding_evidence(request, librarian=librarian)

        called_request = librarian.retrieve.call_args.args[0]
        self.assertEqual(2, called_request.book_scopes[0].chapter_max)

    async def test_started_chapter_one_returns_no_evidence_without_dispatch(self) -> None:
        self._confirm(chapter_max=5)
        librarian = MagicMock()
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=1, chapter_state="started"))

        response = await grounding_evidence(request, librarian=librarian)

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("no_evidence", response.outcome)
        self.assertEqual("none", response.evidence_strength)
        librarian.retrieve.assert_not_called()

    async def test_item_above_ceiling_is_filtered_out(self) -> None:
        self._confirm(chapter_max=5)
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(
            items=[evidence_item("e1", 3), evidence_item("e2", 6)], retrieval_note=""
        )
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=5, chapter_state="completed"))

        judge = self._judge("weak", ("e1",))
        response = await grounding_evidence(
            request, librarian=librarian, strength_judge=judge
        )

        self.assertIsInstance(response, RetrievalResult)
        evidence_ids = {record.evidence_id for record in response.evidence}
        self.assertIn("e1", evidence_ids)
        self.assertNotIn("e2", evidence_ids)
        judged_records = judge.await_args.args[1]
        self.assertEqual(("e1",), tuple(record.evidence_id for record in judged_records))

    async def test_max_final_evidence_clamps_to_five(self) -> None:
        self._confirm(chapter_max=5)
        librarian = MagicMock()
        items = [evidence_item(f"e{i}", 2) for i in range(8)]
        librarian.retrieve.return_value = EvidenceBundle(items=items, retrieval_note="")
        request = build_request(
            "query", WORK_ID, VALID_VERSION,
            ReadingBoundary(chapter_number=5, chapter_state="completed"),
            max_final_evidence=50,
        )

        self.assertEqual(5, request.options.max_final_evidence)
        judge = self._judge("weak", tuple(f"e{i}" for i in range(5)))
        response = await grounding_evidence(
            request, librarian=librarian, strength_judge=judge
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertLessEqual(len(response.evidence), 5)

    async def test_raising_retriever_yields_retrieval_failure(self) -> None:
        self._confirm(chapter_max=5)
        librarian = MagicMock()
        librarian.retrieve.side_effect = RuntimeError("boom")
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=5, chapter_state="completed"))

        response = await grounding_evidence(request, librarian=librarian)

        self.assertIsInstance(response, RetrievalFailure)
        self.assertEqual("retrieval_unavailable", response.error_code)
        self.assertTrue(response.retryable)

    async def test_response_validates_through_adapter(self) -> None:
        self._confirm(chapter_max=5)
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(items=[evidence_item("e1", 2)], retrieval_note="")
        request = build_request("query", WORK_ID, VALID_VERSION, ReadingBoundary(chapter_number=5, chapter_state="completed"))

        response = await grounding_evidence(
            request,
            librarian=librarian,
            strength_judge=self._judge("sufficient", ("e1",)),
        )

        # Round-trips through the discriminated adapter without error.
        LIBRARIAN_RESPONSE_ADAPTER.validate_python(response.model_dump(mode="json"))

    async def test_strength_judge_can_return_sufficient(self) -> None:
        self._confirm()
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(
            items=[evidence_item("e1", 5, "Alice directly explains her confusion.")],
            retrieval_note="",
        )
        request = build_request(
            "Why is Alice confused?",
            WORK_ID,
            VALID_VERSION,
            ReadingBoundary(chapter_number=5, chapter_state="completed"),
        )

        response = await grounding_evidence(
            request,
            librarian=librarian,
            strength_judge=self._judge("sufficient", ("e1",), reason="The passage directly answers the question."),
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("sufficient", response.evidence_strength)
        self.assertEqual(("e1",), tuple(record.evidence_id for record in response.evidence))

    async def test_strength_judge_can_reject_high_scoring_matches_as_none(self) -> None:
        self._confirm()
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(
            items=[evidence_item("e1", 5, "The same words occur without answering the question.")],
            retrieval_note="",
        )
        request = build_request(
            "Why does this happen?",
            WORK_ID,
            VALID_VERSION,
            ReadingBoundary(chapter_number=5, chapter_state="completed"),
        )

        response = await grounding_evidence(
            request,
            librarian=librarian,
            strength_judge=self._judge("none", (), reason="The word overlap does not answer the question."),
        )

        self.assertIsInstance(response, RetrievalResult)
        self.assertEqual("no_evidence", response.outcome)
        self.assertEqual("none", response.evidence_strength)
        self.assertEqual((), response.evidence)

    async def test_strength_judgement_failure_returns_typed_failure(self) -> None:
        self._confirm()
        librarian = MagicMock()
        librarian.retrieve.return_value = EvidenceBundle(
            items=[evidence_item("e1", 5)], retrieval_note=""
        )
        judge = AsyncMock(side_effect=RuntimeError("provider unavailable"))
        request = build_request(
            "identity",
            WORK_ID,
            VALID_VERSION,
            ReadingBoundary(chapter_number=5, chapter_state="completed"),
        )

        response = await grounding_evidence(
            request, librarian=librarian, strength_judge=judge
        )

        self.assertIsInstance(response, RetrievalFailure)
        self.assertEqual("evidence_judgement_unavailable", response.error_code)


class LibrarianSearchToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_arguments_and_returns_response_unchanged(self) -> None:
        from src.linger.agents.muse.tools import librarian_search

        sentinel_response = RetrievalResult(
            kind="result",
            request_id="libreq_x",
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="no evidence",
            searched_scope=SearchedScope(work_id=WORK_ID, book_version_id=VALID_VERSION, max_chapter_inclusive=2),
        )
        boundary = ReadingBoundary(chapter_number=2, chapter_state="completed")

        with patch(
            "src.linger.agents.muse.tools.grounding_evidence",
            new=AsyncMock(return_value=sentinel_response),
        ) as mocked:
            result = await librarian_search("my query", WORK_ID, VALID_VERSION, boundary, max_final_evidence=3)

        self.assertIs(sentinel_response, result)
        mocked.assert_awaited_once()
        (built_request,), _ = mocked.call_args
        self.assertEqual("my query", built_request.query)
        self.assertEqual(WORK_ID, built_request.work_id)
        self.assertEqual(VALID_VERSION, built_request.book_version_id)
        self.assertEqual(boundary, built_request.reading_boundary)

    async def test_built_request_carries_access_scope_and_request_id_muse_did_not_supply(self) -> None:
        from src.linger.agents.muse.tools import librarian_search

        sentinel_response = RetrievalResult(
            kind="result",
            request_id="libreq_x",
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="no evidence",
            searched_scope=SearchedScope(work_id=WORK_ID, book_version_id=VALID_VERSION, max_chapter_inclusive=2),
        )

        with patch(
            "src.linger.agents.muse.tools.grounding_evidence",
            new=AsyncMock(return_value=sentinel_response),
        ) as mocked:
            await librarian_search("q", WORK_ID, VALID_VERSION, None)

        (built_request,), _ = mocked.call_args
        self.assertTrue(built_request.request_id.startswith("libreq_"))
        self.assertIn(VALID_VERSION, built_request.access_scope.allowed_book_version_ids)

    async def test_max_final_evidence_arrives_clamped(self) -> None:
        from src.linger.agents.muse.tools import librarian_search

        sentinel_response = RetrievalResult(
            kind="result",
            request_id="libreq_x",
            outcome="no_evidence",
            evidence_strength="none",
            strength_reason="no evidence",
            searched_scope=SearchedScope(work_id=WORK_ID, book_version_id=VALID_VERSION, max_chapter_inclusive=2),
        )

        with patch(
            "src.linger.agents.muse.tools.grounding_evidence",
            new=AsyncMock(return_value=sentinel_response),
        ) as mocked:
            await librarian_search("q", WORK_ID, VALID_VERSION, None, max_final_evidence=50)

        (built_request,), _ = mocked.call_args
        self.assertEqual(5, built_request.options.max_final_evidence)


class WorkIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_genuinely_different_book_still_clarifies(self) -> None:
        librarian = MagicMock()
        token = set_confirmed_reading(
            ConfirmedReading(work_id="animal-farm", chapter_max=3)
        )
        try:
            response = await grounding_evidence(
                build_request(
                    "identity",
                    WORK_ID,
                    VALID_VERSION,
                    ReadingBoundary(chapter_number=2, chapter_state="completed"),
                ),
                librarian=librarian,
            )
        finally:
            reset_confirmed_reading(token)

        self.assertIsInstance(response, ClarificationRequest)
        self.assertEqual("work_not_confirmed", response.reason_code)
        librarian.retrieve.assert_not_called()

    async def test_allowed_revision_for_a_different_work_fails_before_retrieval(self) -> None:
        librarian = MagicMock()
        librarian.supports_revision.return_value = False
        token = set_confirmed_reading(ConfirmedReading(work_id="animal-farm", chapter_max=3))
        try:
            with self.assertRaises(BookVersionOutOfScope):
                await grounding_evidence(
                    build_request(
                        "power",
                        "animal-farm",
                        VALID_VERSION,
                        ReadingBoundary(chapter_number=3, chapter_state="completed"),
                    ),
                    librarian=librarian,
                )
        finally:
            reset_confirmed_reading(token)

        librarian.retrieve.assert_not_called()
