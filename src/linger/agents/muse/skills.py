"""Muse's explicitly assigned runtime skill."""

from apps.backend.contracts import MuseDraftInput, MuseRevisionInput
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.skills import RuntimeSkill, load_instructions

SHARED_INSTRUCTIONS = load_instructions("src.linger.agents.muse", "shared.md")

REFLECTION: RuntimeSkill[MuseDraftInput | MuseRevisionInput, MuseCandidate] = RuntimeSkill(
    role="Muse",
    name="reflection",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions("src.linger.agents.muse", "skills/reflection/SKILL.md"),
    input_type=MuseDraftInput | MuseRevisionInput,
    output_type=MuseCandidate,
    override_output=False,
    tools=("librarian_route", "librarian_search", "serendipity_explore"),
    validators=("validate_muse_output",),
    output_retries=3,
    tool_retries=1,
)

SKILLS = (REFLECTION,)
