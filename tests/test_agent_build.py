"""Tests for provider-independent agent construction."""

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_ai import Tool
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel

from apps.backend.config import Settings
from src.linger.agents.build import build_agent


def _sample_tool_names(agent) -> set[str]:
    names: set[str] = set()
    for toolset in agent.toolsets:
        names.update(getattr(toolset, "tools", {}).keys())
    return names


def _example_tool(value: int) -> int:
    """A trivial tool used only to test tool registration."""
    return value + 1


class BuildAgentTests(unittest.TestCase):
    def test_requires_explicit_model_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_builds_each_supported_provider(self) -> None:
        cases = (
            (
                "google:gemini-2.5-flash",
                {"google_api_key": "test-key"},
                GoogleModel,
            ),
            (
                "openai:gpt-5",
                {"openai_api_key": "test-key"},
                OpenAIResponsesModel,
            ),
            (
                "anthropic:claude-sonnet-4-5",
                {"anthropic_api_key": "test-key"},
                AnthropicModel,
            ),
        )

        for model_name, credentials, expected_type in cases:
            with self.subTest(model_name=model_name):
                settings = Settings(
                    _env_file=None,
                    linger_model=model_name,
                    **credentials,
                )
                with patch(
                    "src.linger.agents.build.get_settings",
                    return_value=settings,
                ):
                    agent = build_agent("Test instructions")

                self.assertIsInstance(agent.model, expected_type)

    def test_rejects_missing_provider_key(self) -> None:
        for key in (None, "", "   "):
            with self.subTest(key=key):
                settings = Settings(
                    _env_file=None,
                    linger_model="openai:gpt-5",
                    openai_api_key=key,
                )

                with patch(
                    "src.linger.agents.build.get_settings",
                    return_value=settings,
                ):
                    with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                        build_agent("Test instructions")

    def test_rejects_unsupported_or_empty_model(self) -> None:
        for model_name in ("mistral:large", "google:", "gemini-2.5-flash"):
            with self.subTest(model_name=model_name):
                settings = Settings(_env_file=None, linger_model=model_name)
                with patch(
                    "src.linger.agents.build.get_settings",
                    return_value=settings,
                ):
                    with self.assertRaisesRegex(RuntimeError, "Unsupported LINGER_MODEL"):
                        build_agent("Test instructions")

    def test_default_build_agent_has_no_tools(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            agent = build_agent("Test instructions")

        self.assertEqual(set(), _sample_tool_names(agent))

    def test_build_agent_registers_supplied_tools(self) -> None:
        settings = Settings(
            _env_file=None,
            linger_model="google:gemini-2.5-flash",
            google_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            agent = build_agent("Test instructions", tools=[Tool(_example_tool)])

        self.assertIn("_example_tool", _sample_tool_names(agent))


if __name__ == "__main__":
    unittest.main()
