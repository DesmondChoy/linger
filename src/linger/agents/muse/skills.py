"""Muse's explicitly assigned runtime skills."""

from apps.backend.contracts import MuseDraftInput, MuseRevisionInput
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.contracts.triage import TurnNeeds, TurnTriageInput
from src.linger.prompts import load_prompt

SHARED_INSTRUCTIONS = load_prompt("agents", "muse")

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

# Runs before the reflection draft on the current reader message alone. It has
# no tools and grants nothing; the application decides what its result exposes.
TURN_TRIAGE: RuntimeSkill[TurnTriageInput, TurnNeeds] = RuntimeSkill(
    role="Muse",
    name="turn-triage",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions("src.linger.agents.muse", "skills/turn-triage/SKILL.md"),
    input_type=TurnTriageInput,
    output_type=TurnNeeds,
)

SKILLS = (REFLECTION, TURN_TRIAGE)
