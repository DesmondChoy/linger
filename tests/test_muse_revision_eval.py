"""The live revision eval: fixtures are production-valid, the grader and runner measure what they claim."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from evals.muse import revision_run
from evals.muse.revision_run import (
    FixtureError, draft_messages, draft_sentences, grade_revision, load_revision_cases,
    measure, retry_categories, revision_input,
)
from src.linger.agents.muse.agent import validate_muse_output
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.quotation_audit import quoted_response_spans

CASES = load_revision_cases()


@pytest.fixture
def bound():
    """Bind a case's turn context the way the runner does, and always reset it."""
    resets = []

    def bind(case):
        resets.append(revision_run._bind_turn(case))

    yield bind
    for reset in reversed(resets):
        reset()


def by_id(case_id):
    return next(case for case in CASES if case.case_id == case_id)


def test_revision_pack_has_one_case_per_rule_group():
    assert len(CASES) == 6
    assert len({case.case_id for case in CASES}) == 6


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_fixture_draft_replays_through_production_validation(case, bound):
    bound(case)
    messages = asyncio.run(draft_messages(case))
    calls = [part.tool_name for message in messages for part in message.parts
             if isinstance(part, ToolCallPart)]
    assert calls[:-1] == list(case.draft_tool_calls)
    assert calls[-1] == "final_result"
    first = messages[0].parts[0]
    assert isinstance(first, UserPromptPart) and json.loads(first.content)["mode"] == "draft"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_review_block_matches_what_production_would_derive(case):
    sentences = draft_sentences(case)
    draft = MuseCandidate.model_validate(case.draft)
    assert [i for i, s in enumerate(sentences) if s.flagged] == list(case.expect.flagged_sentences)
    assert all(0 <= i < len(sentences) for i in case.review.needs_source_sentences)
    mapped = {claim for use in draft.evidence_uses for claim in use.supported_claims}
    assert set(case.review.previously_accepted_claims) <= mapped
    declared = {(use.source_kind, use.evidence_id) for use in draft.evidence_uses
                if use.source_kind != "session_line"}
    assert {(s.source_kind, s.evidence_id) for s in case.review.retained_sources} <= declared
    quoted = {span.text for span in quoted_response_spans(draft.reply)}
    assert set(case.review.source_quote_interiors) <= quoted
    envelope = json.loads(revision_input(case).model_dump_json())
    assert envelope["mode"] == "revision"
    assert envelope["review"]["released_reader_lines"][-1] == case.reader_message


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_rule_following_reference_passes_grader_and_revision_validation(case, bound):
    bound(case)
    reference = MuseCandidate.model_validate(case.reference_revision)
    context = SimpleNamespace(prompt=revision_input(case).model_dump_json())
    assert validate_muse_output(context, reference) is reference
    assert grade_revision(case, reference) == {"hard_pass": True, "failures": []}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_unrevised_draft_fails_grader(case):
    grade = grade_revision(case, MuseCandidate.model_validate(case.draft))
    assert not grade["hard_pass"]


def test_grader_names_leaked_repair_mechanics():
    case = by_id("muse-revision-quoted-fragment-v1")
    reference = MuseCandidate.model_validate(case.reference_revision)
    leaked = reference.model_copy(update={
        "reply": reference.reply + " I have corrected the wording from my earlier draft.",
    })
    failures = grade_revision(case, leaked)["failures"]
    assert any(failure.startswith("repair_mechanics") for failure in failures)


def test_grader_rejects_reworded_unflagged_sentence_and_unmapped_new_source_content():
    case = by_id("muse-revision-attribution-order-v1")
    reference = MuseCandidate.model_validate(case.reference_revision)
    reworded = reference.model_copy(update={"reply": reference.reply.replace(
        "It is a small moment, but it sets up who listens and who does not.",
        "It is a small moment, but it sets up who listens to Marta and who does not.",
    )})
    failures = grade_revision(case, reworded)["failures"]
    assert any(failure.startswith("unflagged_reworded") for failure in failures)
    assert any(failure.startswith("new_unmapped_source_content") for failure in failures)


def test_grader_rejects_session_line_that_is_not_the_readers_words():
    case = by_id("muse-revision-session-line-v1")
    data = json.loads(json.dumps(case.reference_revision))
    data["evidence_uses"][0]["quote"] = "our club meets on Thursday"
    failures = grade_revision(case, MuseCandidate.model_validate(data))["failures"]
    assert any(failure.startswith("session_line_not_verbatim") for failure in failures)


def test_fixture_draft_that_fails_production_validation_is_rejected(bound):
    case = by_id("muse-revision-unflagged-repeat-v1")
    data = json.loads(case.model_dump_json())
    data["draft"]["evidence_uses"][0]["supported_claims"][0] = "Not a span of the reply."
    broken = type(case).model_validate(data)
    bound(broken)
    with pytest.raises(FixtureError):
        asyncio.run(draft_messages(broken))


def _revision_model(*outputs):
    """Return each output in turn for the revision call; repeat the last."""
    calls = []

    def respond(messages, info):
        output = outputs[min(len(calls), len(outputs) - 1)]
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(respond), calls


def test_runner_reports_a_clean_revision_with_production_envelope_and_history():
    case = by_id("muse-revision-unflagged-repeat-v1")
    model, calls = _revision_model(case.reference_revision)
    report = asyncio.run(measure(model, runs=2, case_ids=[case.case_id]))
    assert report["runs"] == 2 and report["cases"] == 1 and report["errors"] == 0
    assert report["hard_pass_rate"] == 1.0 and report["first_attempt_clean_rate"] == 1.0
    assert report["prompt"]["template_id"] == "muse.revision"
    assert {"digest", "runs", "cases", "errors", "hard_pass_rate", "mean_input_tokens"} <= (
        set(report) | set(report["prompt"])
    )
    run = report["per_case"][case.case_id]["runs"][0]
    assert run["retries"] == 0 and run["tool_calls"] == []
    # The revision sees the replayed draft, then the revision envelope.
    messages = calls[0]
    prompts = [part.content for message in messages for part in message.parts
               if isinstance(part, UserPromptPart)]
    assert [json.loads(prompt)["mode"] for prompt in prompts] == ["draft", "revision"]
    assert any(isinstance(part, ToolCallPart) and part.tool_name == "librarian_search"
               for message in messages for part in message.parts)


def test_runner_classifies_first_attempt_errors_and_counts_retries():
    case = by_id("muse-revision-unflagged-repeat-v1")
    reworded = json.loads(json.dumps(case.reference_revision))
    reworded["reply"] = reworded["reply"].replace(
        "Does his caution seem reasonable to you?", "Does his caution seem sensible to you?",
    )
    model, calls = _revision_model(reworded, case.reference_revision)
    report = asyncio.run(measure(model, runs=1, case_ids=[case.case_id]))
    run = report["per_case"][case.case_id]["runs"][0]
    assert run["hard_pass"] is True
    assert run["retries"] == 1
    assert run["retry_categories"] == [["unflagged_rewrite"]]
    assert report["first_attempt_clean_rate"] == 0.0


def test_runner_counts_exhausted_output_retries_separately_from_passes():
    case = by_id("muse-revision-unflagged-repeat-v1")
    model, calls = _revision_model(case.draft | {"reply": case.draft["reply"] + " Extra."})
    report = asyncio.run(measure(model, runs=1, case_ids=[case.case_id]))
    run = report["per_case"][case.case_id]["runs"][0]
    assert report["errors"] == 1 and report["retry_exhausted"] == 1
    assert run["error"] == "UnexpectedModelBehavior"
    assert run["retries"] >= 3
    assert report["hard_pass_rate"] is None


def test_retry_categories_mark_schema_errors():
    from pydantic_ai.messages import ModelRequest, RetryPromptPart

    message = ModelRequest(parts=[RetryPromptPart(content=[{"type": "missing", "loc": ("reply",), "msg": "x"}])])
    assert retry_categories([message]) == [["schema"]]


def test_retry_categories_name_an_unaddressed_finding(bound):
    from pydantic_ai import ModelRetry
    from pydantic_ai.messages import ModelRequest, RetryPromptPart

    case = by_id("muse-revision-unflagged-repeat-v1")
    bound(case)
    context = SimpleNamespace(prompt=revision_input(case).model_dump_json())
    with pytest.raises(ModelRetry) as caught:
        validate_muse_output(context, MuseCandidate.model_validate(case.draft))
    message = ModelRequest(parts=[RetryPromptPart(content=str(caught.value))])
    assert "unaddressed_finding" in retry_categories([message])[0]


def test_unknown_case_id_is_rejected():
    with pytest.raises(ValueError, match="unknown case"):
        revision_run.select_cases(CASES, ["muse-revision-missing-v1"])
