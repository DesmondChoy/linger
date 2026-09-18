"""Reviewed quotation repairs expose only current, explicitly mapped sources."""

import asyncio
import json

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.muse.agent import build_muse_agent, validate_muse_output
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.skills import REFLECTION
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence
from tests.test_muse_claim_retention import revision_context
from tests.test_muse_quote_repair import record


REQUESTED = "First, be careful."
FRAGMENT = "We are fixing the gate."
SOURCE = 'Mira said, “First, be careful.” Then: “We are fixing\nthe gate,” she added.'


def revision():
    context = revision_context(quotes=(FRAGMENT,))
    envelope = json.loads(context.prompt)
    envelope["muse_turn"]["user_message"] = "Quote Mira's first sentence exactly, then explain her plan."
    context.prompt = json.dumps(envelope)
    return context


def candidate():
    first = f'Mira begins: “{REQUESTED}”'
    second = f'She describes her plan: “{FRAGMENT}”'
    return MuseCandidate.model_validate({
        "reply": first + "\n\n" + second,
        "evidence_uses": [{
            "source_kind": "book_corpus", "evidence_id": "guard-exchange",
            "source_location": "Chapter 1, source lines 1-3",
            "supported_claims": [claim], "exact_quote": quote,
        } for claim, quote in ((first, REQUESTED), (second, None))],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def test_reviewed_fragment_feedback_names_only_its_current_mapped_source():
    output = candidate()
    before = output.model_dump()
    token = set_turn_evidence((record(SOURCE), record(FRAGMENT).model_copy(update={"evidence_id": "unused"})))
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(revision(), output)
        error, = json.loads(str(caught.value))["errors"]
        assert error["quoted_response_text"] == FRAGMENT
        source, = error["current_declared_sources"]
        assert source["declaration_index"] == 1
        assert source["evidence_id"] == "guard-exchange"
        assert source["canonical_source_text"] == SOURCE
        assert source["suggested_quote"] == "We are fixing\nthe gate"
        assert output.model_dump() == before
    finally:
        reset_turn_evidence(token)


def test_unknown_mapping_does_not_borrow_an_available_quote_source():
    output = candidate()
    output = output.model_copy(update={"evidence_uses": (
        output.evidence_uses[0],
        output.evidence_uses[1].model_copy(update={"evidence_id": "unknown"}),
    )})
    token = set_turn_evidence((record(SOURCE),))
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(revision(), output)
        errors = json.loads(str(caught.value))["errors"]
        error = next(item for item in errors if item.get("quoted_response_text") == FRAGMENT)
        assert error["current_declared_sources"] == []
        assert any(item["path"] == "evidence_uses[1].evidence_id" for item in errors)
    finally:
        reset_turn_evidence(token)


def test_function_model_repairs_reviewed_fragment_without_dropping_requested_quote_or_claims():
    initial = candidate()
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        output = initial
        if calls > 1:
            retry = next(part for message in reversed(messages) for part in message.parts
                         if isinstance(part, RetryPromptPart))
            error, = json.loads(retry.content)["errors"]
            quote = error["current_declared_sources"][0]["suggested_quote"]
            second = initial.evidence_uses[1]
            output = initial.model_copy(update={
                "reply": initial.reply.replace(FRAGMENT, quote),
                "evidence_uses": (initial.evidence_uses[0], second.model_copy(update={
                    "exact_quote": quote,
                    "supported_claims": tuple(claim.replace(FRAGMENT, quote) for claim in second.supported_claims),
                })),
            })
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    token = set_turn_evidence((record(SOURCE),))
    try:
        result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
            revision().prompt, **REFLECTION.run_options(),
        ))
        assert validate_muse_output(revision(), result.output) == result.output
    finally:
        reset_turn_evidence(token)
    assert calls == 2
    assert result.output.evidence_uses[0] == initial.evidence_uses[0]
    assert REQUESTED in result.output.reply
    assert len(result.output.evidence_uses) == 2
    assert all(claim in result.output.reply for use in result.output.evidence_uses for claim in use.supported_claims)
