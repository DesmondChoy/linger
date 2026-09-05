"""Tests for the content-free session evidence ledger."""

import json
import unittest
from dataclasses import asdict

from pydantic import ValidationError

from apps.backend import sessions
from src.linger.contracts.turn import ReleaseSource


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


class ReaderStatementTests(unittest.TestCase):
    session_id = "reader-statements-test"
    other_session_id = "reader-statements-other"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)
        sessions.clear(self.other_session_id)

    def append(
        self, text: str, *, release_source: ReleaseSource = "muse_candidate"
    ) -> None:
        sessions.append_turn(
            self.session_id,
            text,
            "Assistant words must not become reader support.",
            turn_id="duplicate-client-turn-id",
            release_source=release_source,
        )

    def test_only_retained_reader_words_are_returned(self) -> None:
        original = "  I reached the Caterpillar.\nI stopped there.  "
        self.append(original)
        self.append("Failed user turn", release_source="application_safe_decline")
        self.append("Private distress", release_source="application_emotional_boundary")
        self.append("Chapter 5?", release_source="application_clarification")
        sessions.append_turn(
            self.other_session_id,
            "Another reader's words",
            "Other reply",
            turn_id="other-turn",
            release_source="muse_candidate",
        )

        statements = sessions.reader_statements(self.session_id)

        self.assertIsInstance(statements, tuple)
        self.assertEqual([original, "Chapter 5?"], [item.text for item in statements])
        self.assertEqual(2, len({item.statement_id for item in statements}))
        self.assertEqual((), sessions.reader_statements("unknown-session"))

    def test_ids_are_stable_as_recent_window_moves_and_turn_ids_repeat(self) -> None:
        for number in range(8):
            self.append(f"Reader message {number}")
        before = sessions.reader_statements(self.session_id)
        self.append("Ninth reader message")
        after = sessions.reader_statements(self.session_id)

        self.assertEqual(8, len(after))
        self.assertEqual(before[1:], after[:-1])
        self.assertNotIn(after[-1].statement_id, {item.statement_id for item in before})
        self.assertEqual("Reader message 0", before[0].text)
        with self.assertRaises(ValidationError):
            before[0].text = "changed"

    def test_total_budget_keeps_complete_contiguous_recent_suffix(self) -> None:
        self.append("older short statement")
        self.append("x" * 15_001)
        self.append("y" * 1_000)

        statements = sessions.reader_statements(self.session_id)

        self.assertEqual(["y" * 1_000], [item.text for item in statements])

    def test_exact_character_budget_preserves_both_complete_statements(self) -> None:
        self.append("x" * 15_000)
        self.append("y" * 1_000)

        statements = sessions.reader_statements(self.session_id)

        self.assertEqual([15_000, 1_000], [len(item.text) for item in statements])

    def test_oversized_latest_statement_does_not_expose_stale_older_context(self) -> None:
        self.append("I finished this book.")
        self.append("x" * 16_001)

        self.assertEqual((), sessions.reader_statements(self.session_id))

    def test_clear_removes_statements_without_mutating_existing_snapshot(self) -> None:
        self.append("A retained reader statement")
        snapshot = sessions.reader_statements(self.session_id)

        sessions.clear(self.session_id)

        self.assertEqual((), sessions.reader_statements(self.session_id))
        self.assertEqual("A retained reader statement", snapshot[0].text)


class ReadingStateTests(unittest.TestCase):
    session_id = "reading-state-test"

    def tearDown(self) -> None:
        sessions.clear(self.session_id)

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
