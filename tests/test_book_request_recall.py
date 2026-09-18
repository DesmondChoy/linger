"""Decomposition must not erase a scoped request before evidence assessment."""

import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.contracts import BookScope, EvidenceBundle, EvidenceItem
from src.linger.agents.librarian.agent import build_librarian_agent
from src.linger.agents.librarian.models import BookRequestPart, BookRequestPlan
from src.linger.orchestration.book_evidence import retrieve_book_evidence


SCOPE = BookScope(work_id="fiction", book_version_id="fiction-v1", chapter_max=3)
LINE = "Quote Mara's refusal. Explain the captain's response. My sister helps me study."
REFUSAL = "Quote Mara's refusal."
RESPONSE = "Explain the captain's response."


def part(text):
    return BookRequestPart(context_spans=(), purpose="answer", reader_spans=(text,))


def item(identity, chapter=3):
    return EvidenceItem(
        evidence_id=identity, work_id="fiction", book_version_id="fiction-v1",
        chapter_id=f"fiction-ch{chapter:02d}", chapter=chapter, location=f"Chapter {chapter}",
        source_title="Fiction", source_sha256="a" * 64, source_lines=(1, 2),
        excerpt=identity, relevance=.1,
    )


def assessment_model(additional=(), *, strength="sufficient", support_ids=("refusal", "response")):
    def model(messages, info):
        payload = json.loads(messages[-1].parts[0].content)
        assert payload["original_request"]["current_line"] == LINE
        assert {e["evidence_id"] for e in payload["evidence"]} == {"refusal", "response"}
        output = {
            "evidence_strength": strength, "strength_reason": "The two book needs are assessed separately.",
            "relevant_evidence_ids": list(support_ids),
            "additional_parts": [part(text).model_dump(mode="json") for text in additional],
            "limitations": ["The captain's response remains unsupported."] if strength == "weak" else [],
            "support": [{"evidence_id": eid, "part_index": index,
                         "necessary_support": "Requested book wording."}
                        for index, eid in enumerate(support_ids)],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
    return build_librarian_agent(FunctionModel(model))


def test_parts_search_independently_and_original_fallback_stays_inside_scope():
    queries = []

    class Librarian:
        def retrieve_for_judgement(self, request):
            queries.append(request.query)
            assert request.book_scopes == [SCOPE]
            found = {REFUSAL: [item("refusal")], RESPONSE: [item("response")], LINE: []}
            return EvidenceBundle(items=found.get(request.query, []), retrieval_note="scoped")

    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request",
              return_value=BookRequestPlan(parts=(part(REFUSAL), part(RESPONSE)))),
        patch("src.linger.agents.librarian.agent.librarian_agent", assessment_model()),
    ):
        result = asyncio.run(retrieve_book_evidence(LINE, book_scopes=(SCOPE,), librarian=Librarian()))
    assert queries == [REFUSAL, RESPONSE, LINE]
    assert result.judgement.evidence_strength == "sufficient"
    assert {i.evidence_id for i in result.items} == {"refusal", "response"}


@pytest.mark.parametrize("retained", [(), (REFUSAL,)])
def test_original_fallback_can_recover_a_need_omitted_by_the_planner(retained):
    queries = []

    class Librarian:
        def retrieve_for_judgement(self, request):
            queries.append(request.query)
            found = [item("refusal"), item("response"), item("forbidden", chapter=4)]
            return EvidenceBundle(items=found if request.query == LINE else [], retrieval_note="scoped")

    additional = tuple(text for text in (REFUSAL, RESPONSE) if text not in retained)
    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request",
              return_value=BookRequestPlan(parts=tuple(part(text) for text in retained))),
        patch("src.linger.agents.librarian.agent.librarian_agent", assessment_model(additional)),
    ):
        result = asyncio.run(retrieve_book_evidence(LINE, book_scopes=(SCOPE,), librarian=Librarian()))
    assert LINE in queries
    assert result.judgement.evidence_strength == "sufficient"
    assert {i.evidence_id for i in result.items} == {"refusal", "response"}


def test_a_newly_noticed_but_unsupported_need_prevents_a_sufficient_result():
    from src.linger.contracts.librarian import EvidenceRecord
    from src.linger.orchestration.evidence_strength import judge_evidence_strength

    records = tuple(EvidenceRecord(
        evidence_id=i.evidence_id, work_id=i.work_id, book_version_id=i.book_version_id,
        chapter_id=i.chapter_id, chapter_number=i.chapter, location=i.location,
        source_sha256=i.source_sha256, source_lines=i.source_lines, text=i.excerpt,
    ) for i in (item("refusal"), item("response")))
    with (
        patch("src.linger.orchestration.evidence_strength.plan_book_request",
              return_value=BookRequestPlan(parts=(part(REFUSAL),))),
        pytest.raises(ValueError, match="every requested part"),
    ):
        asyncio.run(judge_evidence_strength(
            LINE, records, agent=assessment_model((RESPONSE,), support_ids=("refusal",)),
        ))


def test_candidate_budget_preserves_later_needs_and_original_fallback():
    needs = tuple(f"Explain event {index}." for index in range(8))
    original = " ".join(needs)
    searched = []

    class Librarian:
        def retrieve_for_judgement(self, request):
            searched.append(request.query)
            index = needs.index(request.query) if request.query in needs else 8
            return EvidenceBundle(
                items=[item(f"need-{index}-rank-{rank}") for rank in range(5)],
                retrieval_note="Separate candidate streams.",
            )

    def model(messages, info):
        payload = json.loads(messages[-1].parts[0].content)
        observed = {e["evidence_id"] for e in payload["evidence"]}
        assert len(observed) <= 20
        assert {f"need-{index}-rank-0" for index in range(9)} <= observed
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "evidence_strength": "weak", "strength_reason": "Only the last need is supported.",
            "relevant_evidence_ids": ["need-7-rank-0"],
            "limitations": ["The other seven needs remain unresolved."],
            "support": [{"evidence_id": "need-7-rank-0", "part_index": 7,
                         "necessary_support": "The last requested event."}],
        })])

    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request",
              return_value=BookRequestPlan(parts=tuple(part(text) for text in needs))),
        patch("src.linger.agents.librarian.agent.librarian_agent", build_librarian_agent(FunctionModel(model))),
    ):
        result = asyncio.run(retrieve_book_evidence(original, book_scopes=(SCOPE,), librarian=Librarian()))
    assert searched == [*needs, original]
    assert result.judgement.evidence_strength == "weak"
    assert result.judgement.limitations


def test_planning_failure_recovers_within_scope_and_remains_observable():
    class Librarian:
        def retrieve_for_judgement(self, request):
            assert request.query == LINE
            assert request.book_scopes == [SCOPE]
            return EvidenceBundle(items=[item("refusal"), item("response")], retrieval_note="Fallback.")

    with (
        patch("src.linger.orchestration.book_evidence.plan_book_request", side_effect=ValueError("invalid plan")),
        patch("src.linger.orchestration.book_evidence.logfire.warning") as warning,
        patch("src.linger.agents.librarian.agent.librarian_agent", assessment_model((REFUSAL, RESPONSE))),
    ):
        result = asyncio.run(retrieve_book_evidence(LINE, book_scopes=(SCOPE,), librarian=Librarian()))
    warning.assert_called_once_with("librarian.book_request_fallback", reason="planning_unavailable")
    assert result.judgement.evidence_strength == "sufficient"


def test_exact_passage_planning_failure_still_assesses_only_granted_records():
    from src.linger.contracts.librarian import EvidenceRecord
    from src.linger.orchestration.evidence_strength import judge_evidence_strength

    records = tuple(EvidenceRecord(
        evidence_id=i.evidence_id, work_id=i.work_id, book_version_id=i.book_version_id,
        chapter_id=i.chapter_id, chapter_number=i.chapter, location=i.location,
        source_sha256=i.source_sha256, source_lines=i.source_lines, text=i.excerpt,
    ) for i in (item("refusal"), item("response")))
    with patch(
        "src.linger.orchestration.evidence_strength.plan_book_request",
        side_effect=ValueError("invalid plan"),
    ):
        result = asyncio.run(judge_evidence_strength(
            LINE, records, agent=assessment_model((REFUSAL, RESPONSE)),
        ))
    assert result.evidence_strength == "sufficient"
    assert set(result.relevant_evidence_ids) == {record.evidence_id for record in records}
