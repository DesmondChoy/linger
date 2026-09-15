"""Typed inputs and decisions for Librarian's assigned skills."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from src.linger.contracts.base import StrictModel
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.contracts.session import ReaderStatement


class BoundaryMemory(StrictModel):
    """A memory projection without account or storage metadata."""

    memory_id: str
    text: str
    evidence_ids: tuple[str, ...] = ()


class LibrarianBoundaryInferenceInput(StrictModel):
    """Private evidence and reader signals for one boundary judgment."""

    current_line: str
    prior_reader_statements: tuple[ReaderStatement, ...]
    relevant_memories: tuple[BoundaryMemory, ...]
    full_work_candidates: tuple[EvidenceRecord, ...]


class LibrarianBookRequestInput(StrictModel):
    """Reader context without retrieved text or a model-expanded search query."""

    current_line: str
    prior_reader_statements: tuple[ReaderStatement, ...] = ()


class BookRequestPart(StrictModel):
    context_spans: tuple[str, ...] = Field(
        description=(
            "Exact reader fragments identifying the book, scene or speaker needed to "
            "resolve pronouns in reader_spans. Preserve a necessary locator from an "
            "earlier sentence or reader statement. Exclude personal experiences and "
            "other sources. Empty only when reader_spans identify their subject and "
            "scene without additional context. These locators add no answer requirements."
        ),
    )
    purpose: Literal["reference", "answer"] = Field(
        description=(
            "reference: the named book material anchors reflection or a comparison "
            "with another source. answer: the reader asks a book question, asks "
            "to verify a book claim, or requests particular wording. Determine "
            "this from the original reader request before seeing evidence."
        ),
    )
    reader_spans: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "Shortest exact reader fragments naming a requested book event, fact, "
            "interpretation or quotation. Exclude personal experiences, other sources "
            "and reading-progress statements. Split a mixed-source sentence rather "
            "than copying it whole. Never rewrite the reader's words."
        ),
    )


class BookRequestPlan(StrictModel):
    """Book needs identified independently of the available passages."""

    parts: tuple[BookRequestPart, ...]


def book_request_span_errors(
    plan: BookRequestPlan, request: LibrarianBookRequestInput,
) -> list[dict[str, object]]:
    """Report invalid reader anchors; case-only suggestions never grant acceptance."""
    texts = (request.current_line, *(statement.text for statement in request.prior_reader_statements))
    errors: list[dict[str, object]] = []
    for part_index, part in enumerate(plan.parts):
        for field in ("context_spans", "reader_spans"):
            for span_index, span in enumerate(getattr(part, field)):
                if span.strip() and any(span in text for text in texts):
                    continue
                error: dict[str, object] = {
                    "path": f"parts[{part_index}].{field}[{span_index}]",
                    "value": span,
                    "error": "Reader span must be non-empty and copied exactly from supplied reader text.",
                }
                if span.strip():
                    suggestions = {
                        match.group() for text in texts
                        for match in re.finditer(re.escape(span), text, flags=re.IGNORECASE)
                        if match.group().casefold() == span.casefold()
                    }
                    if len(suggestions) == 1:
                        error["suggested_reader_span"] = suggestions.pop()
                errors.append(error)
    return errors


class LibrarianEvidenceStrengthInput(StrictModel):
    """Fixed book needs and exact evidence admitted by retrieval policy."""

    request: BookRequestPlan
    evidence: tuple[EvidenceRecord, ...]
    max_evidence_records: int = Field(default=5, ge=1, le=10)


class EvidenceStrengthDecision(StrictModel):
    """A set-level answerability judgment, independent of retrieval scores."""

    evidence_strength: Literal["sufficient", "weak", "none"]
    strength_reason: str = Field(min_length=1, max_length=2_000)
    relevant_evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _fields_match_strength(self) -> "EvidenceStrengthDecision":
        if self.evidence_strength == "none" and self.relevant_evidence_ids:
            raise ValueError("none strength cannot cite relevant evidence")
        if self.evidence_strength != "none" and not self.relevant_evidence_ids:
            raise ValueError("sufficient or weak strength must cite relevant evidence")
        if self.evidence_strength == "weak" and not self.limitations:
            raise ValueError("weak strength must explain at least one limitation")
        return self


class RequestedBookSupport(StrictModel):
    evidence_id: str = Field(min_length=1)
    part_index: int = Field(ge=0)
    necessary_support: str = Field(min_length=1, max_length=2_000)


class BookEvidenceAssessment(EvidenceStrengthDecision):
    """Every selected record must account for an existing requested part."""

    support: tuple[RequestedBookSupport, ...]

    @model_validator(mode="after")
    def _selection_is_accounted_for(self) -> "BookEvidenceAssessment":
        if {item.evidence_id for item in self.support} != set(self.relevant_evidence_ids):
            raise ValueError("every selected record must map to requested support")
        pairs = [(item.evidence_id, item.part_index) for item in self.support]
        if len(pairs) != len(set(pairs)):
            raise ValueError("requested support mappings must be unique")
        return self


class BoundaryMemoryAssessment(StrictModel):
    """One private judgment of a supplied memory against canonical candidates."""

    memory_id: str = Field(min_length=1)
    status: Literal["grounded_prior_knowledge", "not_supported", "conflicting"]
    evidence_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1, max_length=1000)


class BoundaryInferenceDecision(StrictModel):
    """Private full-work judgment before the application grants retrieval."""

    memory_assessments: tuple[BoundaryMemoryAssessment, ...] = Field(
        description=(
            "Assess every supplied memory exactly once before selecting a boundary. "
            "Ground memory text in full_work_candidates even when its stored evidence_ids "
            "is empty. Empty only when no memories were supplied."
        ),
    )
    outcome: Literal["candidate", "uncertain"]
    work_id: str | None = None
    book_version_id: str | None = None
    chapter_number: int | None = Field(default=None, ge=1)
    confidence: float = Field(ge=0, le=1)
    authorization_basis: Literal["memory_supported", "line_only"] | None = Field(
        default=None,
        description=(
            "Assess supplied memories before choosing. memory_supported combines "
            "grounded earlier knowledge with a coherent, specific current reading "
            "report; the memory need not name the current stopping scene. line_only "
            "means no supplied memory provides that support, not merely that the "
            "current Line identifies the scene on its own. Memory presence alone "
            "does not grant progress; an ambiguous current event remains uncertain."
        ),
    )
    supporting_memory_ids: tuple[str, ...] = Field(
        default=(),
        description=(
            "Exact supplied memory IDs demonstrating earlier knowledge of this work, "
            "located by supporting evidence and consistent with the current report. "
            "Do not omit grounded earlier knowledge because it names a different "
            "scene. Current corrections override older memory claims."
        ),
    )
    supporting_evidence_ids: tuple[str, ...] = Field(
        default=(),
        description=(
            "Exact supplied passages locating both the remembered event and current "
            "reading event for memory_supported decisions, even in the same chapter. "
            "Their latest chapter must equal chapter_number. Never substitute the "
            "memory's location for an unresolved current stopping point."
        ),
    )
    reason_code: Literal[
        "insufficient_context",
        "conflicting_context",
        "low_confidence",
    ] | None = None

    @model_validator(mode="after")
    def _fields_match_outcome(self) -> "BoundaryInferenceDecision":
        errors = boundary_memory_assessment_errors(self)
        if errors:
            raise ValueError(str(errors))
        candidate_fields = (
            self.work_id,
            self.book_version_id,
            self.chapter_number,
        )
        if self.outcome == "candidate":
            if any(value is None for value in candidate_fields):
                raise ValueError("candidate outcome requires work, version, and chapter")
            if not self.supporting_evidence_ids:
                raise ValueError("candidate outcome requires supporting evidence IDs")
            if self.authorization_basis is None:
                raise ValueError("candidate outcome requires an authorization basis")
            if self.authorization_basis == "memory_supported":
                if not self.supporting_memory_ids:
                    raise ValueError(
                        "memory-supported candidate requires supporting memory IDs"
                    )
            elif self.supporting_memory_ids:
                raise ValueError("line-only candidate cannot cite supporting memories")
            if self.reason_code is not None:
                raise ValueError("candidate outcome cannot declare an uncertainty reason")
        else:
            if (
                any(value is not None for value in candidate_fields)
                or self.authorization_basis is not None
                or self.supporting_memory_ids
                or self.supporting_evidence_ids
            ):
                raise ValueError("uncertain outcome cannot declare a candidate boundary")
            if self.reason_code is None:
                raise ValueError("uncertain outcome requires a reason code")
        return self


def boundary_memory_assessment_errors(
    decision: BoundaryInferenceDecision,
    request: LibrarianBoundaryInferenceInput | None = None,
) -> list[dict[str, object]]:
    """Validate declared assessment coverage and consistency, not semantic truth."""
    errors: list[dict[str, object]] = []
    memory_ids = [item.memory_id for item in decision.memory_assessments]
    if len(memory_ids) != len(set(memory_ids)):
        errors.append({"path": "memory_assessments", "error": "Assess each memory exactly once."})
    available_evidence = None
    if request is not None:
        supplied_ids = [memory.memory_id for memory in request.relevant_memories]
        if len(supplied_ids) != len(set(supplied_ids)) or set(memory_ids) != set(supplied_ids):
            errors.append({
                "path": "memory_assessments",
                "error": "Assess every supplied memory once; do not invent or omit memory IDs.",
                "required_memory_ids": supplied_ids,
            })
        available_evidence = {record.evidence_id for record in request.full_work_candidates}
    grounded_ids: set[str] = set()
    grounded_evidence: set[str] = set()
    for index, item in enumerate(decision.memory_assessments):
        path = f"memory_assessments[{index}]"
        if len(item.evidence_ids) != len(set(item.evidence_ids)):
            errors.append({"path": f"{path}.evidence_ids", "error": "Evidence IDs must be unique."})
        if available_evidence is not None and not set(item.evidence_ids) <= available_evidence:
            errors.append({"path": f"{path}.evidence_ids", "error": "Use only supplied canonical evidence IDs."})
        if item.status == "grounded_prior_knowledge":
            if not item.evidence_ids:
                errors.append({"path": f"{path}.evidence_ids", "error": "Grounded prior knowledge requires canonical evidence."})
            grounded_ids.add(item.memory_id)
            grounded_evidence.update(item.evidence_ids)
        elif item.status == "conflicting" and decision.outcome == "candidate":
            errors.append({"path": "outcome", "error": "Conflicting memory support cannot authorize a candidate; return uncertain."})
    if decision.outcome == "candidate":
        if set(decision.supporting_memory_ids) != grounded_ids:
            errors.append({"path": "supporting_memory_ids", "error": "Candidate support must match its grounded memory assessments."})
        expected_basis = "memory_supported" if grounded_ids else "line_only"
        if decision.authorization_basis != expected_basis:
            errors.append({"path": "authorization_basis", "error": f"Declared assessments require {expected_basis}; never promote ungrounded memory."})
        if not grounded_evidence <= set(decision.supporting_evidence_ids):
            errors.append({"path": "supporting_evidence_ids", "error": "Include the canonical anchors for every grounded memory as well as the current event."})
    return errors


class PassageInferenceDecision(StrictModel):
    """Private reading anchors and requested paragraphs are separate selections."""

    outcome: Literal["passages"]
    work_id: str
    book_version_id: str
    confidence: float = Field(ge=0, le=1)
    authorization_basis: Literal["session_supported", "line_only"]
    supporting_statement_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = Field(min_length=1)
    passage_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def _unique_selections(self) -> "PassageInferenceDecision":
        for selected in (
            self.supporting_statement_ids,
            self.supporting_evidence_ids,
            self.passage_evidence_ids,
        ):
            if len(selected) != len(set(selected)):
                raise ValueError("passage inference selections must be unique")
        if self.authorization_basis == "session_supported":
            if not self.supporting_statement_ids:
                raise ValueError(
                    "session-supported passages require supporting statement IDs"
                )
        elif self.supporting_statement_ids:
            raise ValueError("line-only passages cannot cite supporting statements")
        return self


LibrarianBoundaryDecision = BoundaryInferenceDecision | PassageInferenceDecision
