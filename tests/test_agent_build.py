"""Tests for provider selection shared by all role Agent builders."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models import override_allow_model_requests
from openai.types.responses import Response
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel

from apps.backend.config import Settings
from src.linger.agents.build import STANDARD_MODEL, _warn_if_nonstandard, build_model


class BuildModelTests(unittest.TestCase):
    def test_luna_reasoning_setting_reaches_responses_request(self) -> None:
        settings = Settings(
            _env_file=None, linger_model="openai:gpt-6-luna",
            openai_api_key="test-key",
        )
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            model = build_model()
        response = Response.model_validate({
            "id": "resp_local", "created_at": 0, "object": "response",
            "model": "gpt-6-luna", "status": "completed",
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "output": [{
                "id": "msg_local", "type": "message", "role": "assistant",
                "status": "completed", "content": [{
                    "type": "output_text", "text": "Local response", "annotations": [],
                }],
            }],
        })
        create = AsyncMock(return_value=response)
        with patch.object(model.client.responses, "create", create), override_allow_model_requests(True):
            result = asyncio.run(Agent(model).run("Check configured reasoning."))
        self.assertEqual("Local response", result.output)
        self.assertEqual("low", create.await_args.kwargs["reasoning"]["effort"])
        create.assert_awaited_once()

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
                    model = build_model()

                self.assertIsInstance(model, expected_type)
                self.assertFalse(model.settings)

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
                        build_model()

    def test_rejects_unsupported_or_empty_model(self) -> None:
        for model_name in ("mistral:large", "google:", "gemini-2.5-flash"):
            with self.subTest(model_name=model_name):
                settings = Settings(_env_file=None, linger_model=model_name)
                with patch(
                    "src.linger.agents.build.get_settings",
                    return_value=settings,
                ):
                    with self.assertRaisesRegex(RuntimeError, "Unsupported LINGER_MODEL"):
                        build_model()


if __name__ == "__main__":
    unittest.main()


class StandardModelWarningTests(unittest.TestCase):
    def setUp(self) -> None:
        _warn_if_nonstandard.cache_clear()

    def _build(self, linger_model: str, **keys: str) -> None:
        settings = Settings(_env_file=None, linger_model=linger_model, **keys)
        with patch("src.linger.agents.build.get_settings", return_value=settings):
            build_model()

    def test_a_nonstandard_model_warns_once(self) -> None:
        with self.assertLogs("linger.models", level="WARNING") as logs:
            self._build("openai:gpt-5.6-luna", openai_api_key="k")
            self._build("openai:gpt-5.6-luna", openai_api_key="k")
        self.assertEqual(1, len(logs.output))
        self.assertIn(STANDARD_MODEL, logs.output[0])

    def test_the_standard_model_does_not_warn(self) -> None:
        with self.assertNoLogs("linger.models", level="WARNING"):
            self._build(STANDARD_MODEL, openai_api_key="k")
