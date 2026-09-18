"""Explicit assignment of Librarian's model tasks and their contracts."""

from dataclasses import replace

from src.linger.agents.librarian.models import (
    BookEvidenceAssessment,
    BookRequestPlan,
    LibrarianBookRequestInput,
    LibrarianBoundaryDecision,
    LibrarianChapterBoundaryDecision,
    LibrarianBoundaryInferenceInput,
    LibrarianEvidenceStrengthInput,
    LibrarianEventIdentificationInput,
    LibrarianEventIdentification,
)
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.prompts import load_prompt

PACKAGE = "src.linger.agents.librarian"
SHARED_INSTRUCTIONS = load_prompt("agents", "librarian")

BOUNDARY_INFERENCE = RuntimeSkill[
    LibrarianBoundaryInferenceInput, LibrarianBoundaryDecision
](
    role="Librarian",
    name="boundary-inference",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/boundary-inference/SKILL.md"),
    input_type=LibrarianBoundaryInferenceInput,
    output_type=LibrarianBoundaryDecision,
    capabilities=("src.linger.agents.librarian.agent.BoundaryMemoryValidation",),
    validators=(
        "src.linger.agents.librarian.models.boundary_memory_assessment_errors",
        "src.linger.agents.librarian.models.boundary_event_resolution_errors",
        "LibrarianBoundaryDecision",
        "src.linger.orchestration.boundary.infer_spoiler_boundary",
    ),
)

BOUNDARY_INFERENCE_NO_HISTORY = replace(
    BOUNDARY_INFERENCE,
    output_type=LibrarianChapterBoundaryDecision,
    instructions=BOUNDARY_INFERENCE.instructions + "\n\n"
    "Application-selected mode: no earlier reader statements are supplied. "
    "Session-supported passage permission is unavailable. Return a chapter candidate "
    "only when the current event and supplied memories establish its required support; "
    "otherwise return uncertainty. Assess every supplied memory in either outcome. "
    "Do not return a line-only passage location in this mode.",
)

EVENT_IDENTIFICATION = RuntimeSkill[LibrarianEventIdentificationInput, LibrarianEventIdentification](
    role="Librarian",
    name="event-identification",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/event-identification/SKILL.md"),
    input_type=LibrarianEventIdentificationInput,
    output_type=LibrarianEventIdentification,
    capabilities=("src.linger.agents.librarian.agent.EventIdentificationValidation",),
    validators=(
        "src.linger.agents.librarian.models.event_identification_errors",
        "src.linger.orchestration.boundary.infer_spoiler_boundary",
    ),
)

BOOK_REQUEST = RuntimeSkill[LibrarianBookRequestInput, BookRequestPlan](
    role="Librarian",
    name="book-request",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/book-request/SKILL.md"),
    input_type=LibrarianBookRequestInput,
    output_type=BookRequestPlan,
    capabilities=("src.linger.agents.librarian.agent.BookRequestSpanValidation",),
    validators=(
        "src.linger.agents.librarian.models.book_request_span_errors",
        "src.linger.orchestration.evidence_strength.plan_book_request",
    ),
)

EVIDENCE_ASSESSMENT = RuntimeSkill[
    LibrarianEvidenceStrengthInput, BookEvidenceAssessment
](
    role="Librarian",
    name="evidence-assessment",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/evidence-assessment/SKILL.md"),
    input_type=LibrarianEvidenceStrengthInput,
    output_type=BookEvidenceAssessment,
    validators=(
        "BookEvidenceAssessment",
        "src.linger.orchestration.evidence_strength.assess_book_evidence",
    ),
)

SKILLS = (BOUNDARY_INFERENCE, EVENT_IDENTIFICATION, BOOK_REQUEST, EVIDENCE_ASSESSMENT)
