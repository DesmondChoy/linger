"""Explicit assignment of Sculptor's proposal tasks and their contracts."""

from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CurationProposal,
    NoCurationProposal,
    SculptorResponse,
)
from src.linger.agents.sculptor.surfacing_models import (
    Defer,
    DoNotSurface,
    SurfaceNow,
    SurfacingDecision,
    SurfacingInput,
)
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.prompts import load_prompt

PACKAGE = "src.linger.agents.sculptor"
SHARED_INSTRUCTIONS = load_prompt("agents", "sculptor")

MEMORY_CURATION = RuntimeSkill[AccountScopedMemories, SculptorResponse](
    role="Sculptor",
    name="memory-curation",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/memory-curation/SKILL.md"),
    input_type=AccountScopedMemories,
    output_type=(CurationProposal, NoCurationProposal),
    validators=(
        "SCULPTOR_RESPONSE_ADAPTER",
        "src.linger.orchestration.curation.propose_curation",
    ),
)

MEMORY_SURFACING = RuntimeSkill[SurfacingInput, SurfacingDecision](
    role="Sculptor",
    name="memory-surfacing",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/memory-surfacing/SKILL.md"),
    input_type=SurfacingInput,
    output_type=(SurfaceNow, Defer, DoNotSurface),
    validators=(
        "src.linger.agents.sculptor.surfacing_models.validate_surfacing_decision",
    ),
)

SKILLS = (MEMORY_CURATION, MEMORY_SURFACING)
