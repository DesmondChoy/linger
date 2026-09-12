"""Explicit assignment of Librarian's model tasks and their contracts."""

from src.linger.agents.librarian.models import (
    EvidenceStrengthDecision,
    LibrarianBoundaryDecision,
    LibrarianBoundaryInferenceInput,
    LibrarianEvidenceStrengthInput,
)
from src.linger.agents.skills import RuntimeSkill, load_instructions

PACKAGE = "src.linger.agents.librarian"
SHARED_INSTRUCTIONS = load_instructions(PACKAGE, "shared.md")

BOUNDARY_INFERENCE = RuntimeSkill[
    LibrarianBoundaryInferenceInput, LibrarianBoundaryDecision
](
    role="Librarian",
    name="boundary-inference",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/boundary-inference/SKILL.md"),
    input_type=LibrarianBoundaryInferenceInput,
    output_type=LibrarianBoundaryDecision,
    validators=(
        "LibrarianBoundaryDecision",
        "src.linger.orchestration.boundary.infer_spoiler_boundary",
    ),
)

EVIDENCE_ASSESSMENT = RuntimeSkill[
    LibrarianEvidenceStrengthInput, EvidenceStrengthDecision
](
    role="Librarian",
    name="evidence-assessment",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/evidence-assessment/SKILL.md"),
    input_type=LibrarianEvidenceStrengthInput,
    output_type=EvidenceStrengthDecision,
    validators=(
        "EvidenceStrengthDecision",
        "src.linger.orchestration.evidence_strength.judge_evidence_strength",
    ),
)

SKILLS = (BOUNDARY_INFERENCE, EVIDENCE_ASSESSMENT)
