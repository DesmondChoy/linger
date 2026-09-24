"""Typed inputs and decisions for Librarian's assigned skills."""

from __future__ import annotations

import re
from collections import Counter
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


class LibrarianEventIdentificationInput(StrictModel):
    """Locate the reader's current event without a proposed grant or stored memories."""

    current_line: str
    prior_reader_statements: tuple[ReaderStatement, ...]
    full_work_candidates: tuple[EvidenceRecord, ...]


class BoundaryEventIdentified(StrictModel):
    outcome: Literal["identified"]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    reader_spans: tuple[str, ...] = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=700)


class BoundaryEventUnresolved(StrictModel):
    outcome: Literal["unresolved"]
    reason_code: Literal["insufficient_context", "conflicting_context"]
    explanation: str = Field(min_length=1, max_length=700)


LibrarianEventIdentification = BoundaryEventIdentified | BoundaryEventUnresolved


def event_identification_errors(
    decision: LibrarianEventIdentification, request: LibrarianEventIdentificationInput,
) -> list[dict[str, object]]:
    """Bind identification to supplied reader wording and private canonical records."""
    if isinstance(decision, BoundaryEventUnresolved):
        return []
    errors: list[dict[str, object]] = []
    by_id = {record.evidence_id: record for record in request.full_work_candidates}
    if len(set(decision.evidence_ids)) != len(decision.evidence_ids):
        errors.append({"path": "evidence_ids", "error": "Evidence IDs must be unique."})
    for index, identity in enumerate(decision.evidence_ids):
        record = by_id.get(identity)
        if record is None or record.part_id != "main" or record.chapter_number is None:
            errors.append({"path": f"evidence_ids[{index}]", "error": "Select a supplied numbered main-text record."})
    texts = (request.current_line, *(statement.text for statement in request.prior_reader_statements))
    for index, span in enumerate(decision.reader_spans):
        if not span.strip() or not any(span in text for text in texts):
            errors.append({"path": f"reader_spans[{index}]", "error": "Copy a non-empty exact span from the supplied reader wording."})
    if not any(span.strip() and span in request.current_line for span in decision.reader_spans):
        errors.append({"path": "reader_spans", "error": "Include the current reader's stopping-event wording, not only earlier statements."})
    return errors


class LibrarianBookRequestInput(StrictModel):
    """Reader context without retrieved text or a model-expanded search query."""

    current_line: str
    prior_reader_statements: tuple[ReaderStatement, ...] = ()
    search_target: Literal["book_evidence", "reading_progress"] = "book_evidence"


class BookRequestPart(StrictModel):
    context_spans: tuple[str, ...] = Field(
        description=(
            "Exact reader fragments identifying the book, scene or speaker needed to "
            "resolve pronouns in reader_spans. Preserve a necessary locator from an "
            "earlier sentence or reader statement. Exclude personal experiences and "
            "other sources. Empty when reader_spans need no additional locator, "
            "including explicit thematic discovery without a named scene. "
            "These locators add no answer requirements."
        ),
    )
    purpose: Literal["reference", "answer", "progress"] = Field(
        description=(
            "reference: book material anchors reflection or a comparison with another "
            "source, including an explicit request to discover a textual connection. "
            "answer: the reader asks a book question, asks "
            "to verify a book claim, or requests particular wording. Determine "
            "this from the original reader request before seeing evidence. "
            "progress: locate a reported reading event for private boundary judgment."
        ),
    )
    uncertain: bool = Field(default=False, description="A plausible need whose interpretation remains uncertain; still search it.")
    reader_spans: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "Shortest exact reader fragments naming a requested book event, fact, "
            "interpretation or quotation. For explicit title-free discovery, copy the "
            "relevant action or tension as search concepts, without inventing book facts. "
            "Otherwise exclude personal experiences and other sources. For book_evidence, "
            "exclude general reading-progress statements. For "
            "reading_progress, retain the reported event and stopping-point wording. "
            "Split a mixed-source sentence rather than copying it whole. Never rewrite the reader's words."
        ),
    )


class BookRequestPlan(StrictModel):
    """Book needs identified independently of the available passages."""

    parts: tuple[BookRequestPart, ...] = Field(max_length=8)


def book_request_span_errors(
    plan: BookRequestPlan, request: LibrarianBookRequestInput,
) -> list[dict[str, object]]:
    """Report invalid reader anchors; case-only suggestions never grant acceptance."""
    texts = (request.current_line, *(statement.text for statement in request.prior_reader_statements))
    errors: list[dict[str, object]] = []
    for part_index, part in enumerate(plan.parts):
        if (part.purpose == "progress") != (request.search_target == "reading_progress"):
            errors.append({"path": f"parts[{part_index}].purpose", "error": "Part purpose must match the application-selected search target."})
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

    original_request: LibrarianBookRequestInput
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
    """Every selected record supports a planned or recovered reader need."""

    additional_parts: tuple[BookRequestPart, ...] = Field(
        default=(), max_length=8,
        description="Book needs omitted by the plan, copied from original_request. Support indices follow the original planned parts.",
    )
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


class BoundaryEventOccurrence(StrictModel):
    """One possible current reading event, located without disclosing its text."""

    evidence_ids: tuple[str, ...] = Field(min_length=1)
    disposition: Literal["selected", "ruled_out"]
    distinguishing_reader_spans: tuple[str, ...] = Field(
        min_length=1,
        description="Exact current or prior reader wording that identifies or rules out this occurrence; never infer missing details from the passage or a vague memory.",
    )
    explanation: str = Field(min_length=1, max_length=700)


class BoundaryEventResolution(StrictModel):
    """An auditable comparison of occurrences against the original reader input."""

    reader_event_spans: tuple[str, ...] = Field(min_length=1)
    occurrences: tuple[BoundaryEventOccurrence, ...] = Field(min_length=1)
    other_evidence_ids: tuple[str, ...] = Field(
        description="Required inside event_resolution, never at the top level. Every candidate not assigned to event_resolution.occurrences, including earlier memory anchors even when already cited in memory_assessments or supporting_evidence. Use [] only when all candidates are assigned to occurrences. Never hide a plausible alternative here.",
    )

    @model_validator(mode="after")
    def _one_resolved_occurrence(self) -> "BoundaryEventResolution":
        if sum(item.disposition == "selected" for item in self.occurrences) != 1:
            raise ValueError(
                "a candidate requires exactly one identified occurrence; otherwise return uncertain"
            )
        ids = [
            *self.other_evidence_ids,
            *(key for item in self.occurrences for key in item.evidence_ids),
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("account for each candidate evidence ID exactly once")
        if any(not span.strip() for span in self.reader_event_spans) or any(
            not span.strip()
            for item in self.occurrences
            for span in item.distinguishing_reader_spans
        ):
            raise ValueError("reader identification spans cannot be empty")
        return self


class BoundaryEvidenceAnchor(StrictModel):
    """Private source binding for one chapter-permission support record."""

    evidence_id: str = Field(min_length=1)
    source_excerpt: str = Field(
        min_length=1,
        description="Short contiguous excerpt copied from this evidence_id's supplied canonical text, supporting the memory, current event or connecting evidence. Only whitespace may differ. Preserve words, case, punctuation and markup, including original pronouns; never substitute words or copy another record under this ID.",
    )

    @model_validator(mode="after")
    def _nonblank_excerpt(self) -> "BoundaryEvidenceAnchor":
        if not self.source_excerpt.strip():
            raise ValueError("Boundary source excerpt cannot be blank")
        return self


class BoundaryInferenceDecision(StrictModel):
    """A proposed chapter grant with explicit reader identification of the stop."""

    memory_assessments: tuple[BoundaryMemoryAssessment, ...]
    outcome: Literal["candidate"]
    work_id: str
    book_version_id: str
    chapter_number: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    authorization_basis: Literal["memory_supported", "line_only"]
    supporting_memory_ids: tuple[str, ...] = ()
    supporting_evidence: tuple[BoundaryEvidenceAnchor, ...] = Field(min_length=1)
    event_resolution: BoundaryEventResolution

    @model_validator(mode="after")
    def _valid_support(self) -> "BoundaryInferenceDecision":
        errors = boundary_memory_assessment_errors(self)
        if errors:
            raise ValueError(str(errors))
        if (
            self.authorization_basis == "memory_supported"
            and not self.supporting_memory_ids
        ):
            raise ValueError(
                "memory-supported candidate requires supporting memory IDs"
            )
        if self.authorization_basis == "line_only" and self.supporting_memory_ids:
            raise ValueError("line-only candidate cannot cite supporting memories")
        if len({anchor.evidence_id for anchor in self.supporting_evidence}) != len(self.supporting_evidence):
            raise ValueError("Boundary support evidence IDs must be unique")
        selected = next(
            item
            for item in self.event_resolution.occurrences
            if item.disposition == "selected"
        )
        if not set(selected.evidence_ids) <= {anchor.evidence_id for anchor in self.supporting_evidence}:
            raise ValueError(
                "boundary support must include the selected current occurrence"
            )
        return self


class BoundaryUncertainDecision(StrictModel):
    """Unresolved progress, with no fields capable of declaring a chapter grant."""

    memory_assessments: tuple[BoundaryMemoryAssessment, ...]
    outcome: Literal["uncertain"]
    confidence: float = Field(ge=0, le=1)
    reason_code: Literal[
        "insufficient_context", "conflicting_context", "low_confidence"
    ]

    @model_validator(mode="after")
    def _valid_assessments(self) -> "BoundaryUncertainDecision":
        errors = boundary_memory_assessment_errors(self)
        if errors:
            raise ValueError(str(errors))
        return self


def boundary_candidate_inventory_errors(
    output: dict[str, object],
    request: LibrarianBoundaryInferenceInput,
) -> list[dict[str, object]]:
    """Collect canonical excerpt binding, support and inventory faults for one repair."""
    errors: list[dict[str, object]] = []
    if output.get("outcome") != "candidate":
        return errors
    by_id = {item.evidence_id: item for item in request.full_work_candidates}
    support_ids: set[str] = set()
    support = output.get("supporting_evidence")
    if isinstance(support, (list, tuple)):
        for index, anchor in enumerate(support):
            if not isinstance(anchor, dict):
                continue
            identity = anchor.get("evidence_id")
            excerpt = anchor.get("source_excerpt")
            path = f"supporting_evidence[{index}]"
            if not isinstance(identity, str):
                continue
            if identity in support_ids:
                errors.append({"path": f"{path}.evidence_id", "error": "Boundary support evidence IDs must be unique.", "evidence_id": identity})
            support_ids.add(identity)
            record = by_id.get(identity)
            if record is None:
                errors.append({"path": f"{path}.evidence_id", "error": "Use only supplied canonical evidence IDs.", "evidence_id": identity})
            elif (
                not isinstance(excerpt, str)
                or not excerpt.strip()
                or " ".join(excerpt.split()) not in " ".join(record.text.split())
            ):
                errors.append({
                    "path": f"{path}.source_excerpt",
                    "error": "Copy a short nonblank source_excerpt from this named canonical record. Only whitespace may differ: preserve every word, pronoun, letter case, punctuation mark and markup character. Do not correct or paraphrase the source; choose a concise contiguous span that supports the intended event. Recheck the named record rather than attaching another record's words or unrelated text.",
                    "evidence_id": identity,
                })
    assessments = output.get("memory_assessments", [])
    if isinstance(assessments, (list, tuple)):
        if all(isinstance(item, dict) and isinstance(item.get("memory_id"), str)
               for item in assessments):
            supplied_ids = [memory.memory_id for memory in request.relevant_memories]
            memory_ids = [item["memory_id"] for item in assessments]
            counts = Counter(memory_ids)
            missing = sorted(set(supplied_ids) - counts.keys())
            unknown = sorted(counts.keys() - set(supplied_ids))
            duplicated = sorted(identity for identity, count in counts.items() if count > 1)
            if missing or unknown or duplicated:
                errors.append({
                    "path": "memory_assessments",
                    "error": "Assess every supplied memory exactly once; copy its exact memory ID.",
                    "required_memory_ids": supplied_ids,
                    "actual_memory_ids": memory_ids,
                    "missing_memory_ids": missing,
                    "unknown_memory_ids": unknown,
                    "duplicate_memory_ids": duplicated,
                })
            grounded_ids = {
                item["memory_id"] for item in assessments
                if item.get("status") == "grounded_prior_knowledge"
            }
            supporting_ids = output.get("supporting_memory_ids", [])
            if isinstance(supporting_ids, (list, tuple)) and all(
                isinstance(identity, str) for identity in supporting_ids
            ):
                support_counts = Counter(supporting_ids)
                missing = sorted(grounded_ids - support_counts.keys())
                unexpected = sorted(support_counts.keys() - grounded_ids)
                unknown = sorted(support_counts.keys() - set(supplied_ids))
                duplicated = sorted(identity for identity, count in support_counts.items() if count > 1)
                if missing or unexpected or unknown or duplicated:
                    errors.append({
                        "path": "supporting_memory_ids",
                        "error": "Use only exact supplied memory IDs and match the grounded prior-knowledge assessments; do not promote other memories.",
                        "supplied_memory_ids": supplied_ids,
                        "grounded_assessment_memory_ids": sorted(grounded_ids),
                        "actual_memory_ids": list(supporting_ids),
                        "missing_memory_ids": missing,
                        "unexpected_memory_ids": unexpected,
                        "unknown_memory_ids": unknown,
                        "duplicate_memory_ids": duplicated,
                    })
        memory_support = {
            identity
            for assessment in assessments
            if isinstance(assessment, dict) and assessment.get("status") == "grounded_prior_knowledge"
            and isinstance(assessment.get("evidence_ids"), (list, tuple))
            for identity in assessment["evidence_ids"] if isinstance(identity, str)
        }
        missing_memory = sorted(memory_support - support_ids)
        if missing_memory:
            errors.append({"path": "supporting_evidence", "error": "Include a canonical excerpt anchor for every grounded-memory evidence ID.", "missing_evidence_ids": missing_memory})
    if "other_evidence_ids" in output:
        errors.append(
            {
                "path": "other_evidence_ids",
                "error": "Move this field inside event_resolution.other_evidence_ids; it is not a top-level candidate field.",
            }
        )
    resolution = output.get("event_resolution")
    if not isinstance(resolution, dict):
        return errors
    if "other_evidence_ids" not in resolution:
        errors.append(
            {
                "path": "event_resolution.other_evidence_ids",
                "error": "This nested field is required. Include remaining candidate IDs, including earlier memory anchors; do not delete the inventory to repair nesting.",
            }
        )
    other = resolution.get("other_evidence_ids", [])
    occurrences = resolution.get("occurrences", [])
    if not isinstance(other, (list, tuple)) or not isinstance(
        occurrences, (list, tuple)
    ):
        return errors
    ids = list(other)
    for occurrence in occurrences:
        if not isinstance(occurrence, dict) or not isinstance(
            occurrence.get("evidence_ids"), (list, tuple)
        ):
            return errors
        ids.extend(occurrence["evidence_ids"])
    if not all(isinstance(identity, str) for identity in ids):
        return errors
    counts = Counter(ids)
    required = {item.evidence_id for item in request.full_work_candidates}
    missing = sorted(required - counts.keys())
    unknown = sorted(counts.keys() - required)
    duplicated = sorted(identity for identity, count in counts.items() if count > 1)
    if missing or unknown or duplicated:
        errors.append(
            {
                "path": "event_resolution",
                "error": "Account for every supplied candidate exactly once across event_resolution.occurrences[*].evidence_ids and event_resolution.other_evidence_ids. Memory and boundary support citations do not replace this inventory.",
                "missing_evidence_ids": missing,
                "unknown_evidence_ids": unknown,
                "duplicate_evidence_ids": duplicated,
            }
        )
    if isinstance(support, (list, tuple)):
        selected_ids = {
            identity
            for occurrence in occurrences
            if occurrence.get("disposition") == "selected"
            for identity in occurrence["evidence_ids"]
        }
        missing_support = sorted(selected_ids - support_ids)
        if missing_support:
            errors.append({
                "path": "supporting_evidence",
                "error": "Boundary support must include a quoted anchor for every record assigned to the selected current occurrence. Repair the occurrence selection and boundary support together against the reader's actual stopping event.",
                "missing_evidence_ids": missing_support,
            })
    return errors


def boundary_event_resolution_errors(
    decision: BoundaryInferenceDecision,
    request: LibrarianBoundaryInferenceInput,
) -> list[dict[str, object]]:
    """Check occurrence coverage and exact reader anchors, not semantic truth."""
    errors: list[dict[str, object]] = []
    resolution = decision.event_resolution
    reader_texts = (
        request.current_line,
        *(item.text for item in request.prior_reader_statements),
    )
    spans = [
        ("event_resolution.reader_event_spans", span)
        for span in resolution.reader_event_spans
    ]
    spans.extend(
        (f"event_resolution.occurrences[{index}].distinguishing_reader_spans", span)
        for index, item in enumerate(resolution.occurrences)
        for span in item.distinguishing_reader_spans
    )
    for path, span in spans:
        if not any(span in text for text in reader_texts):
            errors.append(
                {
                    "path": path,
                    "error": "Copy an exact current or prior reader span; corpus text and memory alone cannot identify the current occurrence.",
                    "span": span,
                }
            )
    by_id = {item.evidence_id: item for item in request.full_work_candidates}
    errors.extend(boundary_candidate_inventory_errors(decision.model_dump(), request))
    selected = next(
        item for item in resolution.occurrences if item.disposition == "selected"
    )
    records = [by_id[key] for key in selected.evidence_ids if key in by_id]
    if not records or any(
        item.chapter_number is None or item.part_id != "main" for item in records
    ):
        errors.append(
            {
                "path": "event_resolution",
                "error": "The selected current event must have canonical main-text chapter evidence.",
            }
        )
    elif max(item.chapter_number for item in records) != decision.chapter_number:
        errors.append(
            {
                "path": "chapter_number",
                "error": "The identified current stopping event must establish the candidate chapter; an earlier or different memory cannot extend it.",
            }
        )
    return errors


def boundary_memory_assessment_errors(
    decision: BoundaryInferenceDecision | BoundaryUncertainDecision,
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
        if not grounded_evidence <= {anchor.evidence_id for anchor in decision.supporting_evidence}:
            errors.append({"path": "supporting_evidence", "error": "Include the canonical anchors for every grounded memory as well as the current event."})
        if request is not None:
            errors.extend(boundary_event_resolution_errors(decision, request))
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


LibrarianChapterBoundaryDecision = BoundaryInferenceDecision | BoundaryUncertainDecision
LibrarianBoundaryDecision = LibrarianChapterBoundaryDecision | PassageInferenceDecision
