"""Muse's explicitly assigned runtime skills."""

from collections.abc import Collection
from typing import Any

from apps.backend.contracts import MuseDraftInput, MuseRevisionInput
from src.linger.agents.muse.models import MuseCandidate
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.contracts.triage import TurnNeeds, TurnTriageInput
from src.linger.prompts import load_prompt

SHARED_INSTRUCTIONS = load_prompt("agents", "muse")

# The reflection skill is an always-loaded core plus modules the application
# loads per run: `revision` for the revision run, and one module for each tool
# the turn offers. Order is the order they read in the complete text.
_REFLECTION_CORE = load_instructions("src.linger.agents.muse", "skills/reflection/SKILL.md")
_REFLECTION_MODULES = {
    name: load_instructions("src.linger.agents.muse", f"skills/reflection/{name}.md")
    for name in ("revision", "routing", "grounding", "connections")
}
_MODULE_TOOLS = {
    "routing": "librarian_route",
    "grounding": "librarian_search",
    "connections": "serendipity_explore",
}


def reflection_modules(*, revision: bool, tools: Collection[str] | None) -> tuple[str, ...]:
    """Name the reflection modules for one run; `tools=None` means no turn-level gating."""
    return tuple(
        name
        for name in _REFLECTION_MODULES
        if (revision if name == "revision" else tools is None or _MODULE_TOOLS[name] in tools)
    )


def reflection_instructions(*, revision: bool, tools: Collection[str] | None) -> str:
    """Compose the core with the modules this run's mode and offered tools need."""
    names = reflection_modules(revision=revision, tools=tools)
    return "\n\n".join([_REFLECTION_CORE, *(_REFLECTION_MODULES[name] for name in names)])


REFLECTION: RuntimeSkill[MuseDraftInput | MuseRevisionInput, MuseCandidate] = RuntimeSkill(
    role="Muse",
    name="reflection",
    shared_instructions=SHARED_INSTRUCTIONS,
    # The complete text with every module: fingerprints cover all of it, and
    # `reflection_run_options` selects what each run actually sends.
    instructions=reflection_instructions(revision=True, tools=None),
    input_type=MuseDraftInput | MuseRevisionInput,
    output_type=MuseCandidate,
    override_output=False,
    tools=("librarian_route", "librarian_search", "serendipity_explore"),
    validators=("validate_muse_output",),
    output_retries=3,
    tool_retries=1,
)


def reflection_run_options(*, revision: bool, tools: Collection[str] | None) -> dict[str, Any]:
    """Run options whose instructions hold only the modules this run can use."""
    return {
        **REFLECTION.run_options(),
        "instructions": reflection_instructions(revision=revision, tools=tools),
    }


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
