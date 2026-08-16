import unittest

from apps.backend.contracts import (
    BookScope,
    ConnectionBrief,
    ConnectionDecline,
    ConnectionProposal,
    EvidenceBundle,
    LibrarianRequest,
)
from apps.backend.librarian import Librarian
from apps.backend.serendipity import discover
from src.linger.corpus.alice import BOOK_VERSION_ID, WORK_ID


class SerendipityTests(unittest.TestCase):
    def discover(self, brief: ConnectionBrief):
        evidence = Librarian().retrieve(
            LibrarianRequest(
                query=f"{brief.cue} change growing caterpillar myself",
                book_scopes=[
                    BookScope(
                        work_id=WORK_ID,
                        book_version_id=BOOK_VERSION_ID,
                        chapter_max=brief.chapter_max or 1,
                    )
                ],
            )
        )
        return discover(brief, evidence)

    def test_returns_a_supported_identity_connection_at_chapter_five(self) -> None:
        result = self.discover(
            ConnectionBrief(
                cue="Why does the Caterpillar make identity feel unsettling?",
                book_id=WORK_ID,
                chapter_max=5,
            )
        )

        self.assertIsInstance(result, ConnectionProposal)
        assert isinstance(result, ConnectionProposal)
        self.assertEqual(2, len(result.evidence_ids))
        self.assertIn("identity", result.tentative_claim.lower())

    def test_declines_when_the_spoiler_boundary_leaves_too_little_evidence(self) -> None:
        result = self.discover(
            ConnectionBrief(
                cue="Why does the Caterpillar make identity feel unsettling?",
                book_id=WORK_ID,
                chapter_max=2,
            )
        )

        self.assertIsInstance(result, ConnectionDecline)
        assert isinstance(result, ConnectionDecline)
        self.assertEqual(result.reason, "insufficient_evidence")

    def test_declines_for_an_unrecognised_cue(self) -> None:
        result = self.discover(
            ConnectionBrief(
                cue="What colour is the wallpaper?",
                book_id=WORK_ID,
                chapter_max=5,
            )
        )
        self.assertIsInstance(result, ConnectionDecline)

    def test_declines_for_an_unregistered_book(self) -> None:
        result = discover(
            ConnectionBrief(cue="How does identity change?", book_id="unknown-book", chapter_max=5),
            EvidenceBundle(items=[], retrieval_note="No registered corpus."),
        )

        self.assertIsInstance(result, ConnectionDecline)
        assert isinstance(result, ConnectionDecline)
        self.assertEqual(result.reason, "unsupported_cue")


if __name__ == "__main__":
    unittest.main()
