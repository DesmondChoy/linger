"""Provenance's explicit assignments for three independent review tasks."""

from src.linger.agents.provenance.curation_models import (
    CurationProvenanceReview,
    CurationReviewInput,
)
from src.linger.agents.provenance.models import ProvenanceInput, ProvenanceReview
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.contracts.emotional import (
    EmotionalBoundaryAssessment,
    EmotionalBoundaryInput,
)

PACKAGE = "src.linger.agents.provenance"
SHARED_INSTRUCTIONS = load_instructions(PACKAGE, "shared.md")

EMOTIONAL_PREFLIGHT = RuntimeSkill(
    role="Provenance",
    name="emotional-preflight",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/emotional-preflight/SKILL.md"),
    input_type=EmotionalBoundaryInput,
    output_type=EmotionalBoundaryAssessment,
    validators=("EmotionalBoundaryAssessment.model_validate",),
)

CANDIDATE_REVIEW = RuntimeSkill(
    role="Provenance",
    name="candidate-review",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/candidate-review/SKILL.md"),
    input_type=ProvenanceInput,
    output_type=ProvenanceReview,
    validators=(
        "ProvenanceReview.require_decision_specific_justification",
        "ProvenanceInput.validate_review_locations",
    ),
    output_retries=2,
)

CURATION_REVIEW = RuntimeSkill(
    role="Provenance",
    name="curation-review",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/curation-review/SKILL.md"),
    input_type=CurationReviewInput,
    output_type=CurationProvenanceReview,
    validators=(
        "CurationProvenanceReview.require_decision_findings",
        "CurationReviewInput.validate_review",
    ),
)

SKILLS = (EMOTIONAL_PREFLIGHT, CANDIDATE_REVIEW, CURATION_REVIEW)
