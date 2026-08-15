"""Tests for Muse's tool wiring."""

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


if __name__ == "__main__":
    unittest.main()
