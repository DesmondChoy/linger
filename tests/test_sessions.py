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


if __name__ == "__main__":
    unittest.main()
