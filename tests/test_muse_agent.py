"""Tests for Muse's tool wiring and instruction invariants."""

import unittest
from unittest.mock import patch

from apps.backend.config import Settings


def _sample_tool_names(agent) -> set[str]:
    names: set[str] = set()
    for toolset in agent.toolsets:
        names.update(getattr(toolset, "tools", {}).keys())
    return names


class MuseAgentToolWiringTests(unittest.TestCase):
    def test_muse_chat_agent_registers_librarian_search(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            import importlib

            from src.linger.agents.muse import agent as muse_agent_module

            importlib.reload(muse_agent_module)
            try:
                names = _sample_tool_names(muse_agent_module.muse_chat_agent)
                self.assertIn("librarian_search", names)
            finally:
                importlib.reload(muse_agent_module)

    def test_muse_chat_agent_registers_serendipity_explore(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            import importlib

            from src.linger.agents.muse import agent as muse_agent_module

            importlib.reload(muse_agent_module)
            try:
                names = _sample_tool_names(muse_agent_module.muse_chat_agent)
                self.assertIn("serendipity_explore", names)
            finally:
                importlib.reload(muse_agent_module)


class MuseInstructionTests(unittest.TestCase):
    """Guard the load-bearing rules in Muse's Gemini-facing instructions."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.linger.agents.muse.agent import INSTRUCTIONS

        cls.instructions = INSTRUCTIONS

    def test_instructions_are_sectioned_for_structured_prompting(self) -> None:
        headings = {
            line for line in self.instructions.splitlines() if line.startswith("# ")
        }
        self.assertEqual(
            {
                "# Context authority",
                "# Book confirmation and spoilers",
                "# Probe when context is insufficient",
                "# Grounding with librarian_search",
                "# Quotations and honesty",
                "# Connections with serendipity_explore",
            },
            headings,
        )

    def test_instructions_require_probing_when_context_is_insufficient(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("insufficient context", lowered)
        self.assertIn("follow-up question", lowered)
        self.assertIn("guessing", lowered)

    def test_instructions_keep_the_in_scope_identifiers(self) -> None:
        self.assertIn('"alice-adventures-in-wonderland"', self.instructions)
        self.assertIn('"pg11-v01b38ea4"', self.instructions)

    def test_instructions_keep_the_safety_and_honesty_rules(self) -> None:
        lowered = self.instructions.lower()
        self.assertIn("safety authority", lowered)
        self.assertIn("never invent evidence", lowered)
        self.assertIn("spoiler boundary", lowered)
        self.assertIn("until the reader confirms the book", lowered)
        self.assertIn("character names, plot details", lowered)
        self.assertIn("ask the reader that exact question", lowered)
        self.assertIn(
            "never present retrieved text as an exact quotation", lowered
        )
        self.assertIn("relay that honestly", lowered)


if __name__ == "__main__":
    unittest.main()
