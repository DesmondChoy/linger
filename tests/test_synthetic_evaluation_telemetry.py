"""Synthetic-only telemetry may expose content through native Logfire panels."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import logfire
import pytest
from logfire.testing import SimpleSpanProcessor, TestExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.telemetry import (
    EVALUATION_AGENT_NAMES,
    EVALUATION_SERVICE_NAME,
    configure_synthetic_evaluation_telemetry,
)

SYNTHETIC_INSTRUCTIONS = "synthetic system instructions for Logfire"
SYNTHETIC_PROMPT = "synthetic prompt sent to Muse"
SYNTHETIC_RESPONSE = "synthetic response returned by Muse"


def test_synthetic_configuration_is_named_and_content_bearing() -> None:
    agents = tuple(SimpleNamespace(name=name) for name in EVALUATION_AGENT_NAMES) + (
        SimpleNamespace(name="Provenance"),
    )
    with (
        patch("apps.backend.telemetry.get_settings") as get_settings,
        patch.object(logfire, "configure") as configure,
        patch.object(logfire, "instrument_pydantic_ai") as instrument,
    ):
        get_settings.return_value = SimpleNamespace(logfire_token=None)
        configure_synthetic_evaluation_telemetry(agents)

    configure.assert_called_once_with(
        token=None,
        send_to_logfire="if-token-present",
        service_name=EVALUATION_SERVICE_NAME,
        environment="synthetic-evaluation",
        resource_attributes={
            "content.classification": "synthetic",
            "linger.telemetry.mode": "synthetic_evaluation",
        },
        console=False,
        inspect_arguments=False,
        distributed_tracing=False,
    )
    assert instrument.call_count == len(agents)
    for agent in agents:
        instrument.assert_any_call(
            agent,
            include_content=True,
            include_binary_content=False,
            include_model_request_parameters=False,
            version=5,
        )


def test_synthetic_configuration_fails_without_all_five_agents() -> None:
    with pytest.raises(ValueError, match="five named agents"):
        configure_synthetic_evaluation_telemetry(
            (SimpleNamespace(name="Muse"), SimpleNamespace(name="Provenance"))
        )


def test_native_pydantic_ai_spans_include_synthetic_messages() -> None:
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        inspect_arguments=False,
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )

    def respond(_messages, _info):
        return ModelResponse(parts=[TextPart(SYNTHETIC_RESPONSE)])

    agent = Agent(
        FunctionModel(respond),
        name="Muse",
        instructions=SYNTHETIC_INSTRUCTIONS,
    )
    logfire.instrument_pydantic_ai(
        agent,
        include_content=True,
        include_binary_content=False,
        include_model_request_parameters=False,
        version=5,
    )

    asyncio.run(agent.run(SYNTHETIC_PROMPT))

    spans = exporter.exported_spans_as_dict()
    payload = json.dumps(spans, default=str)
    assert any(span["name"] == "invoke_agent Muse" for span in spans)
    assert '"gen_ai.agent.name": "Muse"' in payload
    assert "gen_ai.input.messages" in payload
    assert "gen_ai.output.messages" in payload
    assert "gen_ai.system_instructions" in payload
    assert SYNTHETIC_INSTRUCTIONS in payload
    assert SYNTHETIC_PROMPT in payload
    assert SYNTHETIC_RESPONSE in payload
