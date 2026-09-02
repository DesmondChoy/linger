"""Pin the boundary fields that `spoiler_boundary_clarification` grades.

Grading compares Librarian's inferred ceiling with event-derived Ground truth,
so those fields must keep reaching `TurnInspection.context_resolution`. They are
content-free by contract: a supporting location carries an evidence ID, a
chapter number, and a location string, never post-boundary story text. These
tests fail if a refactor drops a field or lets story content into the ceiling.
"""

import os
import unittest
from unittest.mock import patch

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
    from apps.backend.contracts import ContextResolution
    from apps.backend.schemas import ChatRequest

from src.linger.contracts.librarian import BoundarySupportLocation

SESSION_ID = "boundary-observability-test"
WORK_ID = "pg11"
VERSION_ID = "pg11-v01b38ea4"
PRIVATE_LATER_TEXT = "PRIVATE_LATER_CHAPTER_TEXT_MUST_NOT_ESCAPE"

GRADED_FIELDS = (
    "status",
    "work_id",
    "book_version_id",
    "chapter_max",
    "boundary_source",
    "boundary_confidence",
    "boundary_supporting_locations",
    "candidate_chapter",
    "clarification_question",
)


def inferred_resolution() -> ContextResolution:
    """Mirror what `_apply_boundary_inference` returns for a validated ceiling."""
    return ContextResolution(
        status="confirmed",
        work_id=WORK_ID,
        work_title="Alice's Adventures in Wonderland",
        book_version_id=VERSION_ID,
        chapter_max=5,
        boundary_source="librarian_inferred",
        boundary_confidence=0.93,
        boundary_supporting_locations=(
            BoundarySupportLocation(
                evidence_id=f"{VERSION_ID}-ch05-ln0500-0501",
                chapter_number=5,
                location="Chapter 5, source lines 500-501",
            ),
        ),
        explanation="Librarian privately inferred a ceiling of Chapter 5.",
    )


class BoundaryObservabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        sessions.clear(SESSION_ID)

    def _inspection_for(self, resolution: ContextResolution):
        with patch.object(main, "resolve_reading_context", return_value=resolution):
            inspection, _, _ = main._inspection_for(
                ChatRequest(session_id=SESSION_ID, message="Who is Alice becoming?"),
                allow_memory_capture=False,
            )
        return inspection

    def test_inferred_ceiling_and_its_source_reach_inspection(self) -> None:
        resolution = self._inspection_for(inferred_resolution()).context_resolution

        self.assertEqual(5, resolution["chapter_max"])
        self.assertEqual("librarian_inferred", resolution["boundary_source"])
        self.assertEqual(0.93, resolution["boundary_confidence"])
        self.assertEqual(WORK_ID, resolution["work_id"])
        self.assertEqual(VERSION_ID, resolution["book_version_id"])

    def test_every_graded_boundary_field_is_present(self) -> None:
        """A refactor must not quietly drop a field grading depends on."""
        resolution = self._inspection_for(inferred_resolution()).context_resolution

        missing = [field for field in GRADED_FIELDS if field not in resolution]
        self.assertEqual([], missing)

    def test_supporting_locations_are_content_free(self) -> None:
        """Locating a ceiling must not become a channel for later-chapter text."""
        resolution = self._inspection_for(inferred_resolution()).context_resolution

        supporting = resolution["boundary_supporting_locations"]
        self.assertEqual(1, len(supporting))
        self.assertEqual(
            {"evidence_id", "chapter_number", "location"}, set(supporting[0])
        )

    def test_reader_confirmed_boundary_is_distinguishable_from_inference(self) -> None:
        confirmed = ContextResolution(
            status="confirmed",
            work_id=WORK_ID,
            work_title="Alice's Adventures in Wonderland",
            book_version_id=VERSION_ID,
            chapter_max=3,
            boundary_source="reader_confirmed",
            explanation="The reader confirmed this completed chapter.",
        )
        resolution = self._inspection_for(confirmed).context_resolution

        self.assertEqual("reader_confirmed", resolution["boundary_source"])
        self.assertEqual(3, resolution["chapter_max"])
        self.assertIsNone(resolution["boundary_confidence"])
        self.assertEqual((), tuple(resolution["boundary_supporting_locations"]))

    def test_unresolved_boundary_exposes_a_clarification_without_a_ceiling(self) -> None:
        uncertain = ContextResolution(
            status="inferred",
            work_id=WORK_ID,
            work_title="Alice's Adventures in Wonderland",
            book_version_id=VERSION_ID,
            candidate_chapter=5,
            candidate_confidence=0.4,
            candidate_supporting_locations=(
                BoundarySupportLocation(
                    evidence_id=f"{VERSION_ID}-ch05-ln0500-0501",
                    chapter_number=5,
                    location="Chapter 5, source lines 500-501",
                ),
            ),
            clarification_question="Have you reached the Caterpillar yet?",
            explanation="Librarian could not validate a ceiling with enough confidence.",
        )
        resolution = self._inspection_for(uncertain).context_resolution

        self.assertIsNone(resolution["chapter_max"])
        self.assertIsNone(resolution["boundary_source"])
        self.assertEqual(5, resolution["candidate_chapter"])
        self.assertEqual(
            "Have you reached the Caterpillar yet?",
            resolution["clarification_question"],
        )

    def test_inspection_never_carries_post_boundary_story_text(self) -> None:
        resolution = inferred_resolution().model_copy(
            update={
                "boundary_supporting_locations": (
                    BoundarySupportLocation(
                        evidence_id=f"{VERSION_ID}-ch08-ln0800-0801",
                        chapter_number=8,
                        location="Chapter 8, source lines 800-801",
                    ),
                )
            }
        )
        inspection = self._inspection_for(resolution)

        self.assertNotIn(PRIVATE_LATER_TEXT, inspection.model_dump_json())


if __name__ == "__main__":
    unittest.main()
