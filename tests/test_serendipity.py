import unittest

from apps.backend.contracts import BookScope, ConnectionBrief, ConnectionDecline, ConnectionProposal, LibrarianRequest
from apps.backend.librarian import Librarian
from apps.backend.serendipity import discover


class SerendipityTests(unittest.TestCase):
    def discover(self, brief: ConnectionBrief):
        evidence = Librarian().retrieve(LibrarianRequest(
            query=f"{brief.cue} identity change rule power equal pigs milk",
            book_scopes=[BookScope(book_id=brief.book_id or "", chapter_max=brief.chapter_max or 1)],
        ))
        return discover(brief, evidence)

    def test_returns_a_supported_identity_connection_at_chapter_five(self) -> None:
        result = self.discover(
            ConnectionBrief(
                cue="Why does the Caterpillar make identity feel unsettling?",
                book_id="alice-wonderland",
                chapter_max=5,
            )
        )

        self.assertIsInstance(result, ConnectionProposal)
        assert isinstance(result, ConnectionProposal)
        self.assertGreaterEqual(len(result.evidence_ids), 2)
        self.assertIn("identity", result.tentative_claim.lower())

    def test_declines_when_the_spoiler_boundary_leaves_too_little_evidence(self) -> None:
        result = self.discover(
            ConnectionBrief(
                cue="Why does the Caterpillar make identity feel unsettling?",
                book_id="alice-wonderland",
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
                book_id="alice-wonderland",
                chapter_max=5,
            )
        )

        self.assertIsInstance(result, ConnectionDecline)

    def test_returns_a_power_connection_for_animal_farm(self) -> None:
        result = self.discover(
            ConnectionBrief(cue="How does the milk connect to power and equality?", book_id="animal-farm", chapter_max=3)
        )
        self.assertIsInstance(result, ConnectionProposal)


if __name__ == "__main__":
    unittest.main()
