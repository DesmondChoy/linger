"""Quote hints preserve literal source text; they never waive exact matching."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.muse.agent import build_muse_agent, validate_muse_output
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.muse.skills import REFLECTION
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence


SOURCE = (
    'The guard explained, “We made a mistake; and if the gatekeeper\n'
    'was to learn the truth, we should lose our badges, you know. So\n'
    'we are making repairs before dawn.”'
)
CORE = 'if the gatekeeper\nwas to learn the truth, we should lose our badges'
FULL = CORE + ', you know.'


def record(source):
    return EvidenceRecord(
        evidence_id="guard-exchange", work_id="fiction", book_version_id="fiction-v1",
        chapter_id="fiction-ch1", chapter_number=1,
        location="Chapter 1, source lines 1-3", source_sha256="a" * 64,
        source_lines=(1, 3), text=source,
    )


def candidate(quote):
    return MuseCandidate.model_validate({
        "reply": quote,
        "evidence_uses": [{
            "source_kind": "book_corpus", "evidence_id": "guard-exchange",
            "source_location": "Chapter 1, source lines 1-3",
            "supported_claims": [quote], "exact_quote": quote,
        }],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def quote_error(quote, source):
    output = candidate(quote)
    before = output.model_dump()
    token = set_turn_evidence((record(source),))
    try:
        with pytest.raises(ModelRetry) as caught:
            validate_muse_output(SimpleNamespace(), output)
        error, = json.loads(str(caught.value))["errors"]
        assert error["path"] == "evidence_uses[0].exact_quote"
        assert output.model_dump() == before
        with pytest.raises(ModelRetry):
            validate_muse_output(SimpleNamespace(), output)
        return error
    finally:
        reset_turn_evidence(token)


@pytest.mark.parametrize(("quote", "expected"), [
    ('“' + CORE.replace('\n', ' ') + '.”', CORE),
    ('“' + FULL.replace('\n', ' '), FULL),
    (FULL.replace('\n', ' '), FULL),
    ('and ' + FULL.replace('\n', ' '), 'and ' + FULL),
])
def test_suggests_literal_source_for_whitespace_and_outer_presentation_only(quote, expected):
    error = quote_error(quote, SOURCE)
    assert error["suggested_quote"] == expected
    assert error["suggested_quote"] in SOURCE
    assert "\n" in error["suggested_quote"]
    assert "same words" in error["suggestion_reason"]


@pytest.mark.parametrize(("quote", "source"), [
    ('“' + FULL.replace('\n', ' ').replace('gatekeeper', 'captain') + '”', SOURCE),
    (FULL.replace('\n', ' ').replace('if', 'If', 1), SOURCE),
    (FULL.replace('\n', ' ').replace('truth,', 'truth;'), SOURCE),
    ('We are fixing the gate, rather quietly.', 'We are fixing the gate,\nrather _quietly_.'),
    ("We are fixing the gate because we're afraid.", "We are fixing the gate\nbecause we’re afraid."),
    ('they fled.', 'they\nfled.'),
    ('“...”', SOURCE),
    ('“The group adopted a cat.”', 'The group adopted a catastrophe.'),
    ('“The loss was 12.”', 'The loss was 12.5 units.'),
    ('“The loss was 12.”', 'The loss was 123 units.'),
    ('“The loss was 12.”', 'The loss was 12/50 of the total.'),
    ('“The clock showed 12.”', 'The clock showed 12:50 yesterday.'),
    ('“5 entries remain in the ledger.”', '12.5 entries remain in the ledger.'),
    ('“I think they don.”', "I think they don't agree."),
    ('“The gates belong to James.”', "The gates belong to James's family."),
    ('“The repair needs a long.”', 'The repair needs a long-term plan.'),
    ('“term plan repairs the gate.”', 'The long-term plan repairs the gate.'),
    ('“we mend we mend.”', 'we mend we mend we mend'),
    ('“We must mend the gate.”', 'We must' + ' ' * 2000 + 'mend the gate.'),
    ('“We must mend the gate before dawn.”',
     'We must mend the gate\nbefore dawn. Again: We must mend the gate before dawn.'),
])
def test_declines_changed_words_interior_punctuation_short_or_ambiguous_matches(quote, source):
    error = quote_error(quote, source)
    assert "suggested_quote" not in error
    assert "suggestion_reason" not in error


def test_quote_hint_does_not_drop_the_requested_narration():
    source = '“We are fixing the gate,” Mira said,\nrather _quietly_.'
    error = quote_error(source.replace('\n', ' '), source)
    assert error["suggested_quote"] == source
    assert "Preserve the reader's quotation request" in error["repair"]


def test_function_model_copies_quote_hint_to_both_reply_and_declaration():
    source = '“We are fixing the gate,” Mira said,\nrather _quietly_.'
    original = candidate(source.replace('\n', ' '))
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        output = original
        if calls > 1:
            retry = next(
                part for message in reversed(messages) for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            error, = json.loads(retry.content)["errors"]
            quote = error["suggested_quote"]
            output = original.model_copy(update={
                "reply": quote,
                "evidence_uses": (original.evidence_uses[0].model_copy(update={
                    "exact_quote": quote, "supported_claims": (quote,),
                }),),
            })
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    token = set_turn_evidence((record(source),))
    try:
        result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
            "Quote the reply and the narrator's description of how Mira said it.",
            **REFLECTION.run_options(),
        ))
        assert validate_muse_output(SimpleNamespace(), result.output) is result.output
    finally:
        reset_turn_evidence(token)
    assert calls == 2
    assert result.output.reply == source
    assert result.output.evidence_uses[0].exact_quote == source
    assert original.reply != source
