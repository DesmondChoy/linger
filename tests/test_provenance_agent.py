"""Prompt invariants for the independent Librarian-response release gate."""

import unittest
from unittest.mock import patch

from apps.backend.config import Settings


class ProvenanceLibrarianPolicyTests(unittest.TestCase):
    def test_release_gate_enforces_every_librarian_response_branch(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            import importlib

            from src.linger.agents.provenance import agent as provenance_agent_module

            importlib.reload(provenance_agent_module)
            lowered = " ".join(provenance_agent_module.INSTRUCTIONS.lower().split())
        for branch in ("clarification:", "sufficient:", "weak:", "none:", "failure:"):
            with self.subTest(branch=branch):
                self.assertIn(branch, lowered)

        self.assertIn("does not attempt a book answer", lowered)
        self.assertIn("preserves the stated limitation", lowered)
        self.assertIn("without implying later chapters were searched", lowered)
        self.assertIn("makes no evidence-based book claim", lowered)


if __name__ == "__main__":
    unittest.main()
