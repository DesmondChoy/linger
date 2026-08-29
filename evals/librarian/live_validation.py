"""Credential-backed Librarian-to-Muse release validation.

This evaluation uses the frozen Librarian cases, the selected local hybrid
retriever, the configured evidence-strength model, Muse, Provenance, and the
deterministic application release gate.  The report intentionally stores only
bounded evaluation metadata; prompts, replies, evidence text, and credentials
are excluded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ToolCallPart

from apps.backend import sessions
from apps.backend.chat_turn import prepare_reflection_turn
from apps.backend.config import get_settings
from apps.backend.schemas import ChatRequest
from src.linger.agents.muse.agent import muse_chat_agent
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.contracts.librarian import (
    LIBRARIAN_RESPONSE_ADAPTER,
    RetrievalResult,
)
from src.linger.contracts.turn import ConfirmedReading, ReleaseScope
from src.linger.orchestration.reflection import _tool_results, reflection_reply
from src.linger.orchestration.grounding import librarian_service
from src.linger.orchestration.turn_context import (
    reset_confirmed_reading,
    reset_turn_evidence,
    set_confirmed_reading,
    set_turn_evidence,
)

from evals.librarian.benchmark import (
    MIN_CITATION_PRECISION,
    MIN_EVIDENCE_RECALL,
    BenchmarkCase,
    load_cases,
)


DEFAULT_REPORT = Path(__file__).with_name("live-report.json")
MIN_STRENGTH_ACCURACY = 0.90
MIN_ANSWERABLE_RELEASE_RATE = 0.90


@dataclass
class RecordingAgent:
    """Transparent agent proxy that retains run metadata for this evaluation."""

    agent: Any
    results: list[Any] = field(default_factory=list)

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        result = await self.agent.run(*args, **kwargs)
        self.results.append(result)
        return result


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _overlaps(
    chapter: int,
    source_lines: tuple[int, int],
    gold: tuple[int, int, int],
) -> bool:
    gold_chapter, gold_start, gold_end = gold
    start, end = source_lines
    return chapter == gold_chapter and start <= gold_end and gold_start <= end


def _usage(results: list[Any]) -> dict[str, int | bool | None]:
    totals = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
    for result in results:
        try:
            usage = result.usage()
        except Exception:
            continue
        totals["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        totals["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        totals["requests"] += int(getattr(usage, "requests", 0) or 0)
    if totals["requests"] == 0:
        return {
            "available": False,
            "input_tokens": None,
            "output_tokens": None,
            "requests": None,
        }
    return {"available": True, **totals}


def _chat_message(case: BenchmarkCase) -> str:
    return (
        "I'm reading Alice's Adventures in Wonderland, and I've completed "
        f"chapter {case.chapter_max}. {case.query}"
    )


def _librarian_call_metadata(
    results: list[Any], case: BenchmarkCase
) -> list[dict[str, object]]:
    """Keep request-shape diagnostics without retaining prompt or query text."""
    calls: list[dict[str, object]] = []
    for result in results:
        for message in result.new_messages():
            for part in message.parts:
                if not isinstance(part, ToolCallPart):
                    continue
                if part.tool_name != "librarian_search":
                    continue
                args = part.args_as_dict()
                boundary = args.get("reading_boundary")
                calls.append(
                    {
                        "query_matches_case": args.get("query") == case.query,
                        "work_id_matches": args.get("work_id") == "pg11",
                        "book_version_id_matches": (
                            args.get("book_version_id") == "pg11-v01b38ea4"
                        ),
                        "boundary_chapter": (
                            boundary.get("chapter_number")
                            if isinstance(boundary, dict)
                            else None
                        ),
                        "boundary_state": (
                            boundary.get("chapter_state")
                            if isinstance(boundary, dict)
                            else None
                        ),
                    }
                )
    return calls


async def _run_case(case: BenchmarkCase) -> dict[str, object]:
    session_id = f"librarian-live-eval-{case.case_id}"
    sessions.clear(session_id)
    request = ChatRequest(session_id=session_id, message=_chat_message(case))
    inspection, muse_input, review_context = prepare_reflection_turn(
        request,
        allow_memory_capture=False,
    )
    context = inspection.muse_turn.get("reading_context")
    if not isinstance(context, dict):
        raise RuntimeError(f"{case.case_id}: application did not confirm reading context")

    book_version_id = librarian_service.version_for(str(context["work_id"]))
    if book_version_id is None:
        raise RuntimeError(f"{case.case_id}: no corpus revision for confirmed work")
    release_scope = ReleaseScope(
        work_id=str(context["work_id"]),
        book_version_id=book_version_id,
        chapter_max=int(context["chapter_max"]),
    )

    recording_muse = RecordingAgent(muse_chat_agent)
    recording_provenance = RecordingAgent(provenance_agent)
    token = set_confirmed_reading(
        ConfirmedReading(
            work_id=release_scope.work_id,
            chapter_max=release_scope.chapter_max,
        )
    )
    evidence_token = set_turn_evidence(())
    started = time.perf_counter()
    try:
        release = await reflection_reply(
            muse_input,
            [],
            muse=recording_muse,
            provenance=recording_provenance,
            review_context=review_context,
            release_scope=release_scope,
        )
    finally:
        reset_turn_evidence(evidence_token)
        reset_confirmed_reading(token)
        sessions.clear(session_id)
    latency_ms = (time.perf_counter() - started) * 1_000

    tool_results = [
        item
        for result in recording_muse.results
        for item in _tool_results(result)
    ]
    librarian_calls = _librarian_call_metadata(recording_muse.results, case)
    librarian_results: list[RetrievalResult] = []
    for item in tool_results:
        if item["tool_name"] != "librarian_search":
            continue
        try:
            response = LIBRARIAN_RESPONSE_ADAPTER.validate_python(item["content"])
        except Exception:
            continue
        if isinstance(response, RetrievalResult):
            librarian_results.append(response)

    final_candidate = (
        MuseCandidate.model_validate(recording_muse.results[-1].output)
        if recording_muse.results
        else None
    )
    released_candidate = (
        final_candidate if release.release_source == "muse_candidate" else None
    )

    evidence_by_id = {
        record.evidence_id: record
        for result in librarian_results
        for record in result.evidence
    }
    cited_ids = (
        [item.evidence_id for item in released_candidate.evidence_uses]
        if released_candidate is not None
        else []
    )
    cited_records = [
        evidence_by_id[evidence_id]
        for evidence_id in cited_ids
        if evidence_id in evidence_by_id
    ]
    relevant_citations = [
        record
        for record in cited_records
        if any(
            _overlaps(record.chapter_number, record.source_lines, gold)
            for gold in case.relevant_ranges
        )
    ]
    matched_gold = {
        index
        for index, gold in enumerate(case.recall_ranges)
        if any(
            _overlaps(record.chapter_number, record.source_lines, gold)
            for record in cited_records
        )
    }
    final_recall = (
        len(matched_gold) / len(case.recall_ranges)
        if case.recall_ranges
        else float(not cited_records)
    )
    final_precision = (
        len(relevant_citations) / len(cited_records) if cited_records else 1.0
    )

    strengths = [result.evidence_strength for result in librarian_results]
    predicted_strength = strengths[-1] if strengths else "not_run"
    spoiler_exposure = any(
        record.chapter_number > case.chapter_max
        for result in librarian_results
        for record in result.evidence
    )
    exact_citations_resolve = (
        len(cited_records) == len(cited_ids)
        and release.failure_stage != "deterministic_validation"
    )
    candidate_declarations = []
    if final_candidate is not None:
        for declared in final_candidate.evidence_uses:
            record = evidence_by_id.get(declared.evidence_id)
            candidate_declarations.append(
                {
                    "evidence_id": declared.evidence_id,
                    "resolves": record is not None,
                    "location_matches": (
                        record is not None
                        and declared.source_location == record.location
                    ),
                    "exact_quote_in_reply": (
                        declared.exact_quote is None
                        or declared.exact_quote in final_candidate.reply
                    ),
                    "exact_quote_in_evidence": (
                        declared.exact_quote is None
                        or (
                            record is not None
                            and declared.exact_quote in record.text
                        )
                    ),
                }
            )
    usage = _usage(recording_muse.results + recording_provenance.results)

    return {
        "case_id": case.case_id,
        "expected_strength": case.expected_strength,
        "predicted_strength": predicted_strength,
        "strength_correct": predicted_strength == case.expected_strength,
        "librarian_calls": librarian_calls,
        "release_source": release.release_source,
        "provenance_verdicts": list(release.provenance_verdicts),
        "finding_codes": list(release.finding_codes),
        "failure_stage": release.failure_stage,
        "citation_count": len(cited_ids),
        "relevant_citation_count": len(relevant_citations),
        "cited_evidence_ids": cited_ids,
        "candidate_declarations": candidate_declarations,
        "final_evidence_recall": final_recall,
        "final_citation_precision": final_precision,
        "exact_citations_resolve": exact_citations_resolve,
        "spoiler_exposure": spoiler_exposure,
        "latency_ms": round(latency_ms, 1),
        "usage": usage,
    }


async def run_validation(
    limit: int | None = None, case_ids: set[str] | None = None
) -> dict[str, object]:
    benchmark = load_cases()
    cases = (
        tuple(case for case in benchmark.cases if case.case_id in case_ids)
        if case_ids
        else benchmark.cases
    )
    cases = cases[:limit] if limit is not None else cases
    if not cases:
        raise ValueError("no evaluation cases matched")
    measurements: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
        measurements.append(await _run_case(case))

    latencies = [float(item["latency_ms"]) for item in measurements]
    total_citations = sum(int(item["citation_count"]) for item in measurements)
    total_relevant = sum(
        int(item["relevant_citation_count"]) for item in measurements
    )
    usages = [item["usage"] for item in measurements]
    usage_available = all(bool(usage["available"]) for usage in usages)  # type: ignore[index]
    total_usage: dict[str, bool | int | None] = {"available": usage_available}
    for key in ("input_tokens", "output_tokens", "requests"):
        total_usage[key] = (
            sum(int(usage[key]) for usage in usages)  # type: ignore[index,arg-type]
            if usage_available
            else None
        )
    answerable = [
        item for item in measurements if item["expected_strength"] != "none"
    ]
    evidence_recall = sum(
        float(item["final_evidence_recall"]) for item in measurements
    ) / len(measurements)
    citation_precision = (
        total_relevant / total_citations if total_citations else 1.0
    )
    strength_accuracy = sum(
        bool(item["strength_correct"]) for item in measurements
    ) / len(measurements)
    answerable_release_rate = sum(
        item["release_source"] == "muse_candidate" for item in answerable
    ) / len(answerable)
    spoiler_exposure_count = sum(
        bool(item["spoiler_exposure"]) for item in measurements
    )
    citation_resolution_pass = all(
        bool(item["exact_citations_resolve"]) for item in measurements
    )
    complete_case_set = {case.case_id for case in cases} == {
        case.case_id for case in benchmark.cases
    }
    targets_pass = (
        complete_case_set
        and evidence_recall >= MIN_EVIDENCE_RECALL
        and citation_precision >= MIN_CITATION_PRECISION
        and strength_accuracy >= MIN_STRENGTH_ACCURACY
        and answerable_release_rate >= MIN_ANSWERABLE_RELEASE_RATE
        and spoiler_exposure_count == 0
        and citation_resolution_pass
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": get_settings().linger_model,
        "case_set": "evals/librarian/cases.json",
        "configuration": {
            "retriever": "hybrid_reranked",
            "application_boundary": "reader-confirmed completed chapter",
            "release_path": "Librarian -> Muse -> Provenance -> deterministic validation",
        },
        "targets": {
            "minimum_evidence_recall": MIN_EVIDENCE_RECALL,
            "minimum_citation_precision": MIN_CITATION_PRECISION,
            "minimum_strength_accuracy": MIN_STRENGTH_ACCURACY,
            "minimum_answerable_release_rate": MIN_ANSWERABLE_RELEASE_RATE,
            "maximum_spoiler_exposure_count": 0,
            "exact_citation_resolution_required": True,
        },
        "summary": {
            "case_count": len(measurements),
            "complete_case_set": complete_case_set,
            "targets_pass": targets_pass,
            "evidence_recall": round(evidence_recall, 4),
            "citation_precision": round(citation_precision, 4),
            "strength_accuracy": round(strength_accuracy, 4),
            "answerable_release_rate": round(answerable_release_rate, 4),
            "spoiler_exposure_count": spoiler_exposure_count,
            "citation_resolution_pass": citation_resolution_pass,
            "mean_latency_ms": round(sum(latencies) / len(latencies), 1),
            "p95_latency_ms": round(_p95(latencies), 1),
            "usage": total_usage,
        },
        "cases": measurements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    report = asyncio.run(
        run_validation(args.limit, set(args.case_ids) if args.case_ids else None)
    )
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
