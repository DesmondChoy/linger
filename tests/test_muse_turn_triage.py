"""Muse turn triage: contract, model selection, isolation, and identity."""

import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel

from apps.backend.config import Settings
from src.linger.agents.build import build_triage_model
from src.linger.agents.muse.agent import build_muse_agent
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.skills import REFLECTION, TURN_TRIAGE
from src.linger.contracts.triage import TurnNeeds, TurnTriageInput
from src.linger.orchestration.triage import triage_turn


def test_contract_accepts_independent_needs_and_rejects_anything_else() -> None:
    both = TurnNeeds(book_content="yes", memory="own_earlier_reflections")
    assert (both.book_content, both.memory) == ("yes", "own_earlier_reflections")
    for invalid in (
        {"book_content": "maybe", "memory": "none"},
        {"book_content": "no", "memory": "recall_memory"},
        {"book_content": "no"},
        {"book_content": "no", "memory": "none", "tool": "librarian_route"},
    ):
        with pytest.raises(ValidationError):
            TurnNeeds.model_validate(invalid)
    with pytest.raises(ValidationError):
        TurnTriageInput(current_line="")
    with pytest.raises(ValidationError):
        TurnTriageInput.model_validate({"current_line": "hi", "message_history": []})


@pytest.mark.parametrize(
    ("linger_model", "credentials", "expected_type", "expected_name"),
    (
        ("openai:gpt-5.6-luna", {"openai_api_key": "k"}, OpenAIResponsesModel, "gpt-5.4-mini"),
        ("google:gemini-3.8-pro", {"google_api_key": "k"}, GoogleModel, "gemini-2.5-flash"),
        # No small tier is named for this provider, so triage uses the main model.
        (
            "anthropic:claude-sonnet-4-5",
            {"anthropic_api_key": "k"},
            AnthropicModel,
            "claude-sonnet-4-5",
        ),
    ),
)
def test_triage_model_follows_the_configured_provider(
    linger_model, credentials, expected_type, expected_name
) -> None:
    settings = Settings(_env_file=None, linger_model=linger_model, **credentials)
    with patch("src.linger.agents.build.get_settings", return_value=settings):
        model = build_triage_model()
    assert isinstance(model, expected_type)
    assert model.model_name == expected_name


def test_unknown_provider_fails_like_the_main_model() -> None:
    settings = Settings(_env_file=None, linger_model="mistral:large")
    with patch("src.linger.agents.build.get_settings", return_value=settings):
        with pytest.raises(RuntimeError, match="Unsupported LINGER_MODEL"):
            build_triage_model()


def test_triage_sends_only_the_reader_message_and_no_tools() -> None:
    requests: list[tuple[list[ModelRequest], AgentInfo]] = []

    def triage_model(messages, info: AgentInfo) -> ModelResponse:
        requests.append((messages, info))
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name,
            {"book_content": "unsure", "memory": "none"},
        )])

    def main_model(messages, info: AgentInfo) -> ModelResponse:
        raise AssertionError("triage must run on the per-run model")

    muse = build_muse_agent(FunctionModel(main_model))
    needs = asyncio.run(
        triage_turn("Why did she do that?", muse=muse, model=FunctionModel(triage_model))
    )

    assert needs == TurnNeeds(book_content="unsure", memory="none")
    [(messages, info)] = requests
    [request] = messages
    [prompt] = [part for part in request.parts if isinstance(part, UserPromptPart)]
    assert json.loads(prompt.content) == {"current_line": "Why did she do that?"}
    assert info.function_tools == []
    assert TURN_TRIAGE.instructions in info.instructions
    assert REFLECTION.instructions not in info.instructions


def test_triage_retries_an_output_outside_the_contract() -> None:
    attempts = iter((
        {"book_content": "no", "memory": "serendipity_explore"},
        {"book_content": "no", "memory": "none"},
    ))

    def triage_model(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, next(attempts))])

    muse = build_muse_agent(FunctionModel(triage_model))
    needs = asyncio.run(triage_turn("It rained today.", muse=muse))
    assert needs == TurnNeeds(book_content="no", memory="none")


def test_reflection_keeps_its_tools_and_candidate_checks_beside_triage() -> None:
    seen_tools: list[list[str]] = []
    no_memory = {"kind": "no_memory_candidate", "reason_code": "transient_or_low_signal"}
    candidates = iter((
        # A declared book source the turn never authorised must be sent back.
        {
            "reply": "A plain reply.",
            "evidence_uses": [{
                "source_kind": "book_corpus", "evidence_id": "missing",
                "source_location": "nowhere", "exact_quote": None,
                "supported_claims": ["A plain reply."],
            }],
            "memory": no_memory,
        },
        {"reply": "A plain reply.", "memory": no_memory},
    ))

    def model(messages, info: AgentInfo) -> ModelResponse:
        seen_tools.append(sorted(tool.name for tool in info.function_tools))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, next(candidates))])

    muse = build_muse_agent(FunctionModel(model))
    result = asyncio.run(muse.run("{}", **REFLECTION.run_options()))

    assert isinstance(result.output, MuseCandidate)
    assert result.output.evidence_uses == ()
    assert seen_tools == [sorted(REFLECTION.tools)] * 2


def test_triage_fingerprint_is_registered_and_distinct() -> None:
    from evals.synthetic_journals.replay import RUNTIME_PROMPT_FINGERPRINTS
    from src.linger.agents.muse.prompt import (
        DRAFT_PROMPT_FINGERPRINT,
        TURN_TRIAGE_PROMPT_FINGERPRINT,
    )

    assert TURN_TRIAGE_PROMPT_FINGERPRINT.template_id == "muse.turn-triage"
    assert TURN_TRIAGE_PROMPT_FINGERPRINT in RUNTIME_PROMPT_FINGERPRINTS
    assert TURN_TRIAGE_PROMPT_FINGERPRINT.digest != DRAFT_PROMPT_FINGERPRINT.digest
