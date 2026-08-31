"""Tests for the Muse-facing `librarian_route` tool and its confidence union."""

import unittest
from unittest.mock import patch

from apps.backend.config import Settings
from src.linger.agents.librarian.models import BoundaryInferenceDecision
from src.linger.agents.muse.tools import librarian_route
from src.linger.contracts.librarian import ClarificationRequest, NoMatch, RoutedWork
from src.linger.services.memory import MemoryRecord
from src.linger.orchestration.turn_context import (
    reset_active_memories,
    reset_reader_message,
    set_active_memories,
    set_reader_message,
)


def _book_memory() -> MemoryRecord:
    return MemoryRecord(
        memory_id="memory-alice",
        account_key="account-key",
        text="Alice and the Caterpillar made me think about identity.",
        capture_type="automatic",
        source_event_id="event-alice",
        idempotency_key="key-alice",
        evidence_ids=(),
        created_at="2026-08-28T00:00:00+00:00",
        updated_at="2026-08-28T00:00:00+00:00",
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


if __name__ == "__main__":
    unittest.main()
