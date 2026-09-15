"""Private judgment retains independent search signals within a fixed budget."""

import asyncio
import json
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.linger.agents.librarian.agent import build_librarian_agent

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.hybrid_librarian import HybridLibrarian, _dedupe
from src.linger.agents.librarian.models import EvidenceStrengthDecision
from src.linger.corpus.alice import BOOK_VERSION_ID
from src.linger.orchestration.book_evidence import (
    EvidenceJudgementError,
    retrieve_book_evidence,
    evidence_record_from_item,
)
from test_hybrid_librarian import ConstantEmbedding


class DisagreeingReranker:
    def __init__(self, positive):
        self.positive = positive

    def rerank(self, query, documents):
        assert len(documents) == 6
        scores = [-6, -1, -2, -3, -4, -5]
        return [score + 7 if self.positive else score for score in scores]


@pytest.mark.parametrize("positive", [False, True])
def test_fused_leader_reaches_judge_when_reranked_sixth_and_release_limit_is_one(positive):
    librarian = HybridLibrarian(
        embedding_model=ConstantEmbedding(), reranker=DisagreeingReranker(positive),
    )
    request = LibrarianRequest(
        query="Alice identity",
        book_scopes=[BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)],
        max_results=1,
    )
    candidates = _dedupe(librarian._eligible_windows(request), 6)
    intended = candidates[0]
    judged = []

    async def judge(query, records):
        judged.extend(records)
        assert len(records) == 5
        assert intended.evidence_id in {record.evidence_id for record in records}
        assert candidates[1].evidence_id in {record.evidence_id for record in records}
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="The initial search found the answer.",
            relevant_evidence_ids=(intended.evidence_id,),
        )

    with (
        patch.object(librarian, "_bm25", return_value=candidates),
        patch.object(librarian, "_semantic", return_value=candidates),
    ):
        ordinary = librarian.retrieve(request)
        assert [item.evidence_id for item in ordinary.items] == (
            [candidates[1].evidence_id] if positive else []
        )
        result = asyncio.run(retrieve_book_evidence(
            request.query, book_scopes=tuple(request.book_scopes),
            max_results=request.max_results, librarian=librarian, strength_judge=judge,
        ))

    assert len(judged) == 5
    assert len(result.items) == 1
    assert result.items[0].evidence_id == intended.evidence_id
    assert result.judgement.relevant_evidence_ids == (intended.evidence_id,)


def test_excess_selection_fails_instead_of_truncating_a_set_level_judgement():
    librarian = HybridLibrarian(
        embedding_model=ConstantEmbedding(), reranker=DisagreeingReranker(False),
    )
    request = LibrarianRequest(
        query="Alice identity",
        book_scopes=[BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)],
        max_results=1,
    )
    candidates = _dedupe(librarian._eligible_windows(request), 6)

    async def judge(query, records):
        return EvidenceStrengthDecision(
            evidence_strength="sufficient", strength_reason="Both passages are needed.",
            relevant_evidence_ids=tuple(record.evidence_id for record in records[:2]),
        )

    with (
        patch.object(librarian, "_bm25", return_value=candidates),
        patch.object(librarian, "_semantic", return_value=candidates),
        pytest.raises(EvidenceJudgementError),
    ):
        asyncio.run(retrieve_book_evidence(
            request.query, book_scopes=tuple(request.book_scopes),
            max_results=request.max_results, librarian=librarian, strength_judge=judge,
        ))


@pytest.mark.parametrize("selected_count", [1, 2])
def test_model_receives_release_budget_and_cannot_exceed_it(selected_count):
    from src.linger.orchestration.evidence_strength import judge_evidence_strength

    librarian = HybridLibrarian(
        embedding_model=ConstantEmbedding(), reranker=DisagreeingReranker(False),
    )
    request = LibrarianRequest(
        query="Alice identity",
        book_scopes=[BookScope(work_id="pg11", book_version_id=BOOK_VERSION_ID, chapter_max=5)],
        max_results=1,
    )
    candidates = _dedupe(librarian._eligible_windows(request), 6)
    with (
        patch.object(librarian, "_bm25", return_value=candidates),
        patch.object(librarian, "_semantic", return_value=candidates),
    ):
        records = tuple(evidence_record_from_item(item) for item in librarian.retrieve_for_judgement(request).items)

    model_inputs = []
    plan = {"parts": [{"context_spans": [], "purpose": "answer", "reader_spans": [request.query]}]}

    async def model(messages, info):
        payload = json.loads(messages[-1].parts[0].content)
        model_inputs.append(payload)
        if "current_line" in payload:
            assert payload == {"current_line": request.query, "prior_reader_statements": []}
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, plan)])
        assert set(payload) == {"request", "evidence", "max_evidence_records"}
        assert payload["request"] == plan
        assert payload["max_evidence_records"] == 1
        assert len(payload["evidence"]) == 5
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "evidence_strength": "sufficient", "strength_reason": "Selected support.",
            "relevant_evidence_ids": [record.evidence_id for record in records[:selected_count]],
            "support": [{
                "evidence_id": record.evidence_id, "part_index": 0,
                "necessary_support": "Selected support for the requested answer.",
            } for record in records[:selected_count]],
        })])

    invocation = judge_evidence_strength(
        request.query, records, max_evidence_records=1,
        agent=build_librarian_agent(FunctionModel(model)),
    )
    if selected_count == 2:
        with pytest.raises(ValueError, match="selection budget"):
            asyncio.run(invocation)
    else:
        result = asyncio.run(invocation)
        assert result.relevant_evidence_ids == (records[0].evidence_id,)
    assert len(model_inputs) == 2
