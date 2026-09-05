"""Tests for the content-free session evidence ledger."""

import json
import unittest
from dataclasses import asdict

from apps.backend import sessions


class SessionEvidenceLedgerTests(unittest.TestCase):
    session_id = "session-evidence-ledger-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    def test_muse_candidate_grants_exact_deduplicated_evidence_ids(self) -> None:
        sessions.append_turn(
            self.session_id,
            "question",
            "released answer",
            turn_id="turn-1",
            release_source="muse_candidate",
            evidence_ids=("evidence-1", "evidence-1", "evidence-2"),
            review_finding_codes=((),),
        )

        self.assertEqual(
            ("evidence-1", "evidence-2"),
            sessions.released_evidence_ids(self.session_id),
        )
        self.assertEqual(
            ("evidence-1", "evidence-2"),
            sessions.turn_records(self.session_id)[0].evidence_ids,
        )

    def test_safe_decline_is_audited_but_grants_no_evidence(self) -> None:
        private_passage = "PRIVATE_REJECTED_PASSAGE_8d3a"
        sessions.append_turn(
            self.session_id,
            private_passage,
            "safe decline",
            turn_id="turn-2",
            release_source="application_safe_decline",
            evidence_ids=("evidence-1",),
            review_finding_codes=(("unsupported_claim", "spoiler"),),
        )

        record = sessions.turn_records(self.session_id)[0]
        self.assertEqual((), sessions.released_evidence_ids(self.session_id))
        self.assertEqual(("evidence-1",), record.evidence_ids)
        self.assertEqual(
            (("unsupported_claim", "spoiler"),),
            record.review_finding_codes,
        )
        self.assertNotIn(private_passage, json.dumps(asdict(record)))
        self.assertEqual([], sessions.history(self.session_id))

    def test_emotional_boundary_is_audited_but_grants_no_evidence(self) -> None:
        sessions.append_turn(
            self.session_id,
            "private distressing Line",
            "fixed boundary",
            turn_id="turn-boundary",
            release_source="application_emotional_boundary",
            evidence_ids=("evidence-1",),
        )

        self.assertEqual((), sessions.released_evidence_ids(self.session_id))
        self.assertEqual(
            "application_emotional_boundary",
            sessions.turn_records(self.session_id)[0].release_source,
        )
        self.assertEqual([], sessions.history(self.session_id))

    def test_decline_between_released_turns_leaves_history_at_four_messages(
        self,
    ) -> None:
        sessions.append_turn(
            self.session_id,
            "first question",
            "first released answer",
            turn_id="turn-released-1",
            release_source="muse_candidate",
        )
        sessions.append_turn(
            self.session_id,
            "private distressing Line",
            "fixed boundary",
            turn_id="turn-declined",
            release_source="application_emotional_boundary",
        )
        sessions.append_turn(
            self.session_id,
            "second question",
            "second released answer",
            turn_id="turn-released-2",
            release_source="muse_candidate",
        )

        self.assertEqual(4, len(sessions.history(self.session_id)))

    def test_clear_removes_evidence_audit_and_grants(self) -> None:
        sessions.append_turn(
            self.session_id,
            "question",
            "released answer",
            turn_id="turn-3",
            release_source="muse_candidate",
            evidence_ids=("evidence-1",),
        )

        sessions.clear(self.session_id)

        self.assertEqual((), sessions.turn_records(self.session_id))
        self.assertEqual((), sessions.released_evidence_ids(self.session_id))


class ReadingStateTests(unittest.TestCase):
    session_id = "reading-state-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

    def test_switching_books_discards_the_previous_books_pending_question(self) -> None:
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id="pg11"))
        sessions.set_pending_clarification(
            self.session_id,
            sessions.PendingClarification(book_id="pg11", reason_code="insufficient_context"),
        )
        sessions.set_book_selection(self.session_id, sessions.BookSelection(book_id="pg12"))
        self.assertIsNone(sessions.pending_clarification(self.session_id))

    def test_restore_reading_state_rolls_back_a_pending_clarification(self) -> None:
        sessions.set_pending_clarification(
            self.session_id,
            sessions.PendingClarification(book_id="pg11", book_title="Alice", reason_code="insufficient_context"),
        )
        snapshot = sessions.snapshot_reading_state(self.session_id)
        sessions.set_pending_clarification(
            self.session_id,
            sessions.PendingClarification(book_id="pg12", book_title="Other", reason_code="ambiguous_scene"),
        )

        sessions.restore_reading_state(self.session_id, snapshot)

        restored = sessions.pending_clarification(self.session_id)
        self.assertEqual("pg11", restored.book_id)
        self.assertEqual("insufficient_context", restored.reason_code)

    def test_clear_drops_a_pending_clarification(self) -> None:
        sessions.set_pending_clarification(
            self.session_id,
            sessions.PendingClarification(book_id="pg11", book_title="Alice", reason_code="insufficient_context"),
        )

        sessions.clear(self.session_id)

        self.assertIsNone(sessions.pending_clarification(self.session_id))


if __name__ == "__main__":
    unittest.main()
