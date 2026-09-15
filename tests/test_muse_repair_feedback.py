"""One Muse repair sees every mechanical citation problem in the candidate."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.muse.agent import build_muse_agent, validate_muse_output
from src.linger.agents.muse.models import MuseCandidate, validate_supported_claims
from src.linger.agents.muse.skills import REFLECTION
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.turn_context import reset_turn_evidence, set_turn_evidence


URL = "https://example.org/reporting-study"
WEB_CLAIM = "The essay describes reporting errors."
BOOK = EvidenceRecord(
    evidence_id="book-exchange", work_id="fiction", book_version_id="fiction-v1",
    chapter_id="fiction-ch1", chapter_number=1,
    location="Chapter 1, source lines 1-2", source_sha256="a" * 64,
    source_lines=(1, 2), text="“We’re fixing it,” she said,\nrather _quietly_.",
)


@pytest.fixture(autouse=True)
def evidence_ledger():
    token = set_turn_evidence((BOOK,))
    try:
        yield
    finally:
        reset_turn_evidence(token)


def broken_candidate():
    return MuseCandidate.model_validate({
        "reply": f"“Fixing it,” she said, rather quietly. {WEB_CLAIM}",
        "evidence_uses": [
            {
                "source_kind": "book_corpus", "evidence_id": BOOK.evidence_id,
                "source_location": "Chapter 1",
                "supported_claims": ["She is fixing it."],
                "exact_quote": "We’re fixing it",
            },
            {
                "source_kind": "web", "evidence_id": URL,
                "supported_claims": ["The essay describes reporting errors;"],
            },
        ],
        "memory": {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"},
    })


def feedback_for(candidate):
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(SimpleNamespace(), candidate)
    return json.loads(str(caught.value))


def test_one_retry_identifies_every_mismatched_field_and_its_exact_value():
    candidate = broken_candidate()
    original = candidate.model_dump()
    feedback = feedback_for(candidate)
    errors = {error["path"]: error for error in feedback["errors"]}

    assert set(errors) == {
        "evidence_uses[0].supported_claims[0]",
        "evidence_uses[1].supported_claims[0]",
        "evidence_uses[0].source_location",
        "evidence_uses[0].exact_quote",
        "evidence_uses[1].evidence_id",
    }
    assert errors["evidence_uses[0].supported_claims[0]"]["value"] == "She is fixing it."
    assert errors["evidence_uses[1].supported_claims[0]"]["value"] == "The essay describes reporting errors;"
    assert errors["evidence_uses[0].source_location"]["expected"] == BOOK.location
    quote_error = errors["evidence_uses[0].exact_quote"]
    assert quote_error["value"] == "We’re fixing it"
    assert quote_error["quote_in_reply"] is False
    assert quote_error["quote_in_source"] is True
    assert quote_error["canonical_book_evidence"] == BOOK.model_dump(mode="json")
    assert errors["evidence_uses[1].evidence_id"]["value"] == URL
    assert "Preserve the reader's quotation request" in str(feedback)
    assert "do not replace a requested quotation with a paraphrase" in str(feedback)
    assert candidate.model_dump() == original
    with pytest.raises(ValueError, match="supported_claims"):
        validate_supported_claims(candidate.reply, candidate.evidence_uses)


@pytest.mark.parametrize(("reply", "quote", "in_reply", "in_source"), [
    ("She waited.", "She waited.", True, False),
    ("She waited.", "A different sentence.", False, False),
    ("She waited.", BOOK.text, False, True),
])
def test_quote_feedback_distinguishes_reply_from_source_mismatch(reply, quote, in_reply, in_source):
    candidate = broken_candidate().model_copy(update={
        "reply": reply,
        "evidence_uses": (broken_candidate().evidence_uses[0].model_copy(update={
            "supported_claims": (reply,), "source_location": BOOK.location,
            "exact_quote": quote,
        }),),
    })
    error, = feedback_for(candidate)["errors"]
    assert error["path"] == "evidence_uses[0].exact_quote"
    assert error["quote_in_reply"] is in_reply
    assert error["quote_in_source"] is in_source
    assert error["canonical_book_evidence"]["text"] == BOOK.text


def test_unknown_book_does_not_hide_later_citation_errors():
    candidate = broken_candidate()
    candidate = candidate.model_copy(update={"evidence_uses": (
        candidate.evidence_uses[0].model_copy(update={"evidence_id": "unknown-book"}),
        candidate.evidence_uses[1],
    )})
    errors = {error["path"]: error for error in feedback_for(candidate)["errors"]}
    assert errors["evidence_uses[0].evidence_id"]["value"] == "unknown-book"
    assert errors["evidence_uses[1].evidence_id"]["value"] == URL
    assert "evidence_uses[0].supported_claims[0]" in errors
    assert "evidence_uses[1].supported_claims[0]" in errors


@pytest.mark.parametrize("claims", [
    (),
    (" ",),
    (WEB_CLAIM, WEB_CLAIM),
    (WEB_CLAIM, "A stale second claim."),
])
def test_release_and_model_feedback_share_mapping_checks(claims):
    candidate = broken_candidate()
    candidate = candidate.model_copy(update={
        "reply": f"{WEB_CLAIM} [Study]({URL})",
        "evidence_uses": (candidate.evidence_uses[1].model_copy(update={
            "supported_claims": claims,
        }),),
    })
    errors = feedback_for(candidate)["errors"]
    assert errors
    assert all(error["path"].startswith("evidence_uses[0].supported_claims") for error in errors)
    if len(claims) == 2:
        assert errors[0]["path"] == "evidence_uses[0].supported_claims[1]"
    with pytest.raises(ValueError, match="supported_claims"):
        validate_supported_claims(candidate.reply, candidate.evidence_uses)


def test_function_model_repairs_all_reported_problems_in_one_attempt():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        output = broken_candidate()
        if calls > 1:
            retry = next(
                part for message in reversed(messages) for part in message.parts
                if isinstance(part, RetryPromptPart)
            )
            errors = {error["path"]: error for error in json.loads(retry.content)["errors"]}
            assert len(errors) == 5
            source = errors["evidence_uses[0].exact_quote"]["canonical_book_evidence"]
            url = errors["evidence_uses[1].evidence_id"]["value"]
            output = output.model_copy(update={
                "reply": f'{source["text"]} {WEB_CLAIM} [Study]({url})',
                "evidence_uses": (
                    output.evidence_uses[0].model_copy(update={
                        "source_location": source["location"],
                        "exact_quote": source["text"], "supported_claims": (source["text"],),
                    }),
                    output.evidence_uses[1].model_copy(update={"supported_claims": (WEB_CLAIM,)}),
                ),
            })
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
        "Quote the exchange including the narrator's description, and compare the essay.",
        **REFLECTION.run_options(),
    ))
    assert calls == 2
    assert result.output.evidence_uses[0].exact_quote == BOOK.text
    assert BOOK.text in result.output.reply
    assert WEB_CLAIM in result.output.reply
    assert validate_muse_output(SimpleNamespace(), result.output) is result.output


def inline_citation_candidate(claim=WEB_CLAIM, prose=WEB_CLAIM[:-1]):
    candidate = broken_candidate()
    return candidate.model_copy(update={
        "reply": f"{prose} [Study]({URL}).",
        "evidence_uses": (candidate.evidence_uses[1].model_copy(update={
            "supported_claims": (claim,),
        }),),
    })


@pytest.mark.parametrize("punctuation", [".", ";", "?", "!"])
def test_citation_punctuation_hint_is_literal_and_does_not_accept_the_original(punctuation):
    claim = WEB_CLAIM[:-1] + punctuation
    candidate = inline_citation_candidate(claim=claim)
    original = candidate.model_dump()
    feedback = feedback_for(candidate)
    error, = feedback["errors"]

    assert error["value"] == claim
    assert error["suggested_span"] == WEB_CLAIM[:-1]
    assert error["suggested_span"] in candidate.reply
    assert "terminal punctuation" in error["suggestion_reason"]
    assert "citation" in feedback["repair"]
    assert candidate.model_dump() == original
    with pytest.raises(ValueError, match="supported_claims"):
        validate_supported_claims(candidate.reply, candidate.evidence_uses)
    with pytest.raises(ModelRetry):
        validate_muse_output(SimpleNamespace(), candidate)


@pytest.mark.parametrize(("claim", "prose"), [
    (WEB_CLAIM, WEB_CLAIM[:-1].lower()),
    ("The essay describes errors.", WEB_CLAIM[:-1]),
    ("The essay describes a cat.", "The essay describes a catastrophe"),
    ("cat.", "A bobcat"),
    ("The rate is 12.", "The rate is 123"),
    ("The rate is 12!", "The rate is 12.5"),
    ("5 entries remain.", "12.5 entries remain"),
    ("The gates belong to James.", "The gates belong to James's family"),
    ("The gates belong to James.", "The gates belong to James’s family"),
    ("The plan is long.", "The plan is long-term"),
    ("term plan.", "A long-term plan"),
    ("...", "A substantive claim"),
])
def test_punctuation_hint_does_not_change_words_case_or_match_a_word_prefix(claim, prose):
    error, = feedback_for(inline_citation_candidate(claim, prose))["errors"]
    assert "suggested_span" not in error
    assert "suggestion_reason" not in error


def test_function_model_explicitly_adopts_the_citation_punctuation_suggestion():
    original = inline_citation_candidate()
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
            output = original.model_copy(update={"evidence_uses": (
                original.evidence_uses[0].model_copy(update={
                    "supported_claims": (error["suggested_span"],),
                }),
            )})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"))])

    result = asyncio.run(build_muse_agent(FunctionModel(model)).run(
        "Explain the study with a visible citation.", **REFLECTION.run_options(),
    ))
    assert calls == 2
    assert result.output.reply == original.reply
    assert result.output.evidence_uses[0].supported_claims == (WEB_CLAIM[:-1],)
    assert original.evidence_uses[0].supported_claims == (WEB_CLAIM,)
