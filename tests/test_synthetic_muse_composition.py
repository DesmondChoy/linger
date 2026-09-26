"""The authoring experiment must remove copy work without removing guards."""

from types import SimpleNamespace
import asyncio

import pytest
from pydantic_ai import ModelRetry, ToolOutput
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from evals.synthetic_journals.muse_composition import (
    MuseComposition, compile_composition, compose_muse_output,
)
from evals.synthetic_journals.muse_stage_replay import book_record_from_tool, history_before_first_output
from src.linger.contracts.connection_evidence import WebConnectionEvidence
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection, register_connection_evidence, reset_connection_inspection,
)


URL = "https://example.org/essay"
MEMORY = {"kind": "no_memory_candidate", "reason_code": "automatic_capture_disabled"}
SOURCE = {"source_kind": "web", "evidence_id": URL}


def composition(*segments):
    return MuseComposition(segments=segments, memory=MEMORY)


def test_text_written_once_yields_exact_supported_and_limit_spans():
    claim = f"The essay describes passing moods ([Essay]({URL}))."
    limit = "The essay does not say whether a promise lapses."
    candidate = compile_composition(composition(
        {"kind": "supported", "text": claim, "sources": [SOURCE]},
        {"kind": "limit", "text": limit, "sources": [SOURCE]},
        {"kind": "reflection", "text": "What remains important?", "paragraph_break": True},
    ))
    assert candidate.reply == f"{claim} {limit}\n\nWhat remains important?"
    use, = candidate.evidence_uses
    assert use.supported_claims == (claim,)
    assert use.limit_claims == (limit,)


def test_joint_limit_is_projected_to_every_named_record():
    second = {"source_kind": "memory", "evidence_id": "memory-1"}
    candidate = compile_composition(composition(
        {"kind": "supported", "text": "The essay describes moods.", "sources": [SOURCE]},
        {"kind": "supported", "text": "Your note describes a promise.", "sources": [second]},
        {"kind": "limit", "text": "Neither record establishes that the promise lapses.",
         "sources": [SOURCE, second]},
    ))
    assert all(use.limit_claims == ("Neither record establishes that the promise lapses.",)
               for use in candidate.evidence_uses)


def test_limit_only_source_cannot_evade_existing_candidate_contract():
    with pytest.raises(ModelRetry, match="supported source account"):
        compile_composition(composition(
            {"kind": "limit", "text": "The essay does not say.", "sources": [SOURCE]},
        ))


def test_unknown_sources_and_invented_quotes_still_use_production_checks():
    token = begin_connection_inspection()
    try:
        value = composition({"kind": "supported", "text": f"Essay ([Essay]({URL})).", "sources": [SOURCE]})
        with pytest.raises(ModelRetry, match="authorized source ID"):
            compose_muse_output(SimpleNamespace(prompt=""), value)
        register_connection_evidence([WebConnectionEvidence(evidence_id=URL, title="Essay", excerpt="Passing moods.")])
        invented = composition({"kind": "supported", "text": f'The essay says "Unchanging moods." ([Essay]({URL})).',
                                "sources": [{**SOURCE, "exact_quote": "Unchanging moods."}]})
        with pytest.raises(ModelRetry, match="quotation must occur exactly"):
            compose_muse_output(SimpleNamespace(prompt=""), invented)
    finally:
        reset_connection_inspection(token)


def test_reflection_cannot_carry_source_refs():
    with pytest.raises(ValueError, match="reflection must not claim source support"):
        composition({"kind": "reflection", "text": "A question?", "sources": [SOURCE]})


def test_direct_librarian_records_keep_their_original_contract():
    from src.linger.contracts.librarian import EvidenceRecord

    record = EvidenceRecord(
        evidence_id="book-ch1-lines1-2", work_id="book", book_version_id="v1",
        chapter_id="chapter-1", chapter_number=1, part_id="main", location="Chapter 1",
        source_sha256="a" * 64, source_lines=(1, 2), text="A promise was made.",
    )
    assert book_record_from_tool("librarian_search", record.model_dump(mode="json")) == record


def test_projection_keeps_retrieval_but_excludes_failed_output_and_repair():
    earlier = {"kind": "response", "parts": [{"part_kind": "tool-call", "tool_name": "final_result"}]}
    prompt = {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "current envelope"}]}
    retrieval = {"kind": "request", "parts": [{"part_kind": "tool-return", "tool_name": "serendipity_explore"}]}
    output = {"kind": "response", "parts": [{"part_kind": "tool-call", "tool_name": "final_result"}]}
    retry = {"kind": "request", "parts": [{"part_kind": "retry-prompt"}]}
    exchange = SimpleNamespace(
        input_prompt="current envelope", message_history=[earlier],
        model_messages=[prompt, retrieval, output, retry], model_messages_include_history=False,
    )
    assert history_before_first_output(exchange) == [earlier, prompt, retrieval]
    exchange.model_messages_include_history = True
    exchange.model_messages = [earlier, prompt, retrieval, output, retry]
    assert history_before_first_output(exchange) == [earlier, prompt, retrieval]


def test_experimental_output_function_retries_and_returns_normal_candidate():
    from src.linger.agents.muse.agent import build_muse_agent
    from src.linger.agents.muse.models import MuseCandidate
    from src.linger.orchestration.turn_context import ToolExposure, reset_tool_exposure, set_tool_exposure

    calls = []

    def model(messages, info):
        assert not info.function_tools
        calls.append(messages)
        source = SOURCE if len(calls) > 1 else {**SOURCE, "evidence_id": "https://example.org/unknown"}
        value = composition({"kind": "supported", "text": f"The essay describes passing moods ([Essay]({URL})).", "sources": [source]})
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, value.model_dump(mode="json"))])

    async def run():
        inspection = begin_connection_inspection()
        exposure = set_tool_exposure(ToolExposure(frozenset()))
        try:
            register_connection_evidence([WebConnectionEvidence(evidence_id=URL, title="Essay", excerpt="Passing moods.")])
            result = await build_muse_agent(FunctionModel(model)).run(
                "Write a short comparison.", output_type=ToolOutput(compose_muse_output),
            )
            assert isinstance(result.output, MuseCandidate)
            assert len(calls) == 2
        finally:
            reset_tool_exposure(exposure)
            reset_connection_inspection(inspection)

    asyncio.run(run())
