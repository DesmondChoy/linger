"""Repair missing visible web citations before Muse leaves its model run."""

import asyncio

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.muse.agent import build_muse_agent
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.skills import REFLECTION


URL = "https://example.org/reporting-errors"
SECOND_URL = "https://example.org/team-climate"
CLAIM = "The study describes conditions associated with reporting errors."
CITATION = f"[Reporting study]({URL})"


def candidate(citation, urls=(URL,)):
    return MuseCandidate.model_validate({
        "reply": f"{CLAIM} {citation}".strip(),
        "evidence_uses": [{
            "source_kind": "web", "evidence_id": url,
            "supported_claims": [CLAIM],
        } for url in urls],
        "memory": {
            "kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled",
        },
    })


@pytest.mark.parametrize("initial_citation", [
    "",
    URL,
    f"[Other study]({SECOND_URL})",
    f"[Different page]({URL}/different)",
    CITATION,
])
def test_muse_repairs_missing_exact_markdown_citation_before_return(initial_citation):
    calls = []

    async def model(messages, info):
        calls.append(messages)
        if len(calls) > 1:
            retries = [part for message in messages for part in message.parts if isinstance(part, RetryPromptPart)]
            assert retries
            assert "citation" in str(retries[-1].content)
        output = candidate(initial_citation if len(calls) == 1 else CITATION)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
        "What does the reporting study say?", **REFLECTION.run_options(),
    ))

    assert len(calls) == (1 if initial_citation == CITATION else 2)
    assert result.output.reply == f"{CLAIM} {CITATION}"
    assert result.output.evidence_uses[0].supported_claims == (CLAIM,)


def test_citing_one_declared_page_does_not_cover_another():
    calls = []
    complete_citations = f"{CITATION} [Team climate]({SECOND_URL})"

    async def model(messages, info):
        calls.append(messages)
        output = candidate(
            CITATION if len(calls) == 1 else complete_citations,
            urls=(URL, SECOND_URL),
        )
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
        "Compare the two studies.", **REFLECTION.run_options(),
    ))

    assert len(calls) == 2
    assert result.output.reply == f"{CLAIM} {complete_citations}"


def test_persistent_missing_citation_exhausts_existing_output_retry_budget():
    calls = []

    async def model(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, candidate("").model_dump(mode="json"))])

    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        asyncio.run(build_muse_agent(FunctionModel(model)).run(
            "What does the reporting study say?", **REFLECTION.run_options(),
        ))
    assert len(calls) == 4
