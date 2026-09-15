"""Prompt invariants for the independent Librarian-response release gate."""

import unittest

from src.linger.agents.provenance.prompt import INSTRUCTIONS


class ProvenanceLibrarianPolicyTests(unittest.TestCase):
    def test_prompt_scopes_each_librarian_response_branch_to_its_support(self) -> None:
        lowered = " ".join(INSTRUCTIONS.lower().split())
        for branch in ("clarification:", "sufficient:", "weak:", "none:", "failure:"):
            with self.subTest(branch=branch):
                self.assertIn(branch, lowered)

        self.assertIn("claims that rely on that call", lowered)
        self.assertIn("forbids a book answer", lowered)
        self.assertIn("another tool result cannot widen authority", lowered)
        self.assertIn("preserve the stated limitations wherever they remain unresolved", lowered)
        self.assertIn("without implying later chapters were searched", lowered)
        self.assertIn(
            "without other supporting canonical records, permit no evidence-based book answer",
            lowered,
        )
        self.assertIn(
            "an empty, weak, or failed direct search does not invalidate a different "
            "authorized record in `canonical_book_evidence`",
            lowered,
        )


if __name__ == "__main__":
    unittest.main()
