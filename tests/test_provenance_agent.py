"""Prompt invariants for the independent Librarian-response release gate."""

import unittest

from src.linger.agents.provenance.prompt import INSTRUCTIONS


class ProvenanceLibrarianPolicyTests(unittest.TestCase):
    def test_release_gate_enforces_every_librarian_response_branch(self) -> None:
        lowered = " ".join(INSTRUCTIONS.lower().split())
        for branch in ("clarification:", "sufficient:", "weak:", "none:", "failure:"):
            with self.subTest(branch=branch):
                self.assertIn(branch, lowered)

        self.assertIn("does not attempt a book answer", lowered)
        self.assertIn("preserves the stated limitation", lowered)
        self.assertIn("without implying later chapters were searched", lowered)
        self.assertIn("makes no evidence-based book claim", lowered)


if __name__ == "__main__":
    unittest.main()
