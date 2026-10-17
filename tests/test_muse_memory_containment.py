"""Muse's memory nomination must be a verbatim, non-blank span of the reader's message."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from apps.backend.contracts import (
    ContextResolution, MuseDraftInput, MuseRevisionInput, MuseRevisionReview, MuseTurn, TurnPolicy,
)
from src.linger.agents.provenance.models import RiskFinding
from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.models import MuseCandidate

MESSAGE = (
    "Some of the books I read are Alice in Wonderland, Pinocchio, "
    "I want to read them again but I don't have the time"
)


def draft_context(message: str = MESSAGE) -> SimpleNamespace:
    envelope = MuseDraftInput(
        mode="draft",
        muse_turn=MuseTurn(
            turn_id="t", user_message=message, reading_context=None,
            policy=TurnPolicy(allow_retrieval=False, allow_connection=False),
        ),
        context_resolution=ContextResolution(status="unknown", explanation="Test context."),
    )
    return SimpleNamespace(prompt=envelope.model_dump_json())


def revision_context(message: str = MESSAGE) -> SimpleNamespace:
    envelope = MuseRevisionInput(
        mode="revision",
        muse_turn=MuseTurn(
            turn_id="t", user_message=message, reading_context=None,
            policy=TurnPolicy(allow_retrieval=False, allow_connection=False),
        ),
        context_resolution=ContextResolution(status="unknown", explanation="Test context."),
        review=MuseRevisionReview(
            findings=(RiskFinding(
                code="unsupported_claim", applies_to="response",
                location={"kind": "structural", "source_field": "candidate.response", "path": ""},
                explanation="Soften the claim.",
            ),),
            previously_accepted_claims=(),
            source_quote_interiors=(),
            released_reader_lines=(),
        ),
    )
    return SimpleNamespace(prompt=envelope.model_dump_json())


def candidate(text: str) -> MuseCandidate:
    return MuseCandidate.model_validate({
        "reply": "That sounds like a pull worth keeping.",
        "memory": {"kind": "memory_candidate", "text": text, "reason_code": "durable_reflection"},
    })


def test_a_verbatim_span_passes():
    output = candidate("I want to read them again but I don't have the time")
    assert validate_muse_output(draft_context(), output) is output


def test_the_whole_message_passes():
    output = candidate(MESSAGE)
    assert validate_muse_output(draft_context(), output) is output


def test_a_paraphrase_is_retried_with_a_repair_instruction():
    with pytest.raises(ModelRetry) as retry:
        validate_muse_output(draft_context(), candidate("I would like to reread those books"))
    payload = json.loads(retry.value.message)
    error = next(e for e in payload["errors"] if e["path"] == "memory.text")
    assert error["value"] == "I would like to reread those books"
    assert "character for character" in error["repair"]
    assert "shortest span" in error["repair"]


def test_the_revision_run_checks_containment_too():
    output = candidate(MESSAGE)
    assert validate_muse_output(revision_context(), output) is output
    with pytest.raises(ModelRetry) as retry:
        validate_muse_output(revision_context(), candidate("I would like to reread those books"))
    assert any(e["path"] == "memory.text" for e in json.loads(retry.value.message)["errors"])


def test_whitespace_only_text_is_rejected():
    with pytest.raises(ModelRetry) as retry:
        validate_muse_output(draft_context("a  b"), candidate("  "))
    assert any(e["path"] == "memory.text" for e in json.loads(retry.value.message)["errors"])


def test_a_plain_text_prompt_skips_the_containment_check():
    output = candidate("not in any envelope")
    assert validate_muse_output(SimpleNamespace(prompt="plain text"), output) is output


def test_offsets_are_no_longer_part_of_the_contract():
    with pytest.raises(ValidationError):
        MuseCandidate.model_validate({
            "reply": "Reply.",
            "memory": {"kind": "memory_candidate", "text": "x", "start_codepoint": 0,
                       "end_codepoint": 1, "reason_code": "durable_reflection"},
        })
