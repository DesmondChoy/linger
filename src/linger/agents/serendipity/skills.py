"""Serendipity's explicitly assigned runtime skill."""

from src.linger.agents.serendipity.models import (
    ConnectionDecline,
    ConnectionDiscoveryInput,
    ConnectionProposal,
    SerendipityResponse,
)
from src.linger.agents.skills import RuntimeSkill, load_instructions

SHARED_INSTRUCTIONS = load_instructions("src.linger.agents.serendipity", "shared.md")

CONNECTION_DISCOVERY: RuntimeSkill[ConnectionDiscoveryInput, SerendipityResponse] = RuntimeSkill(
    role="Serendipity",
    name="connection-discovery",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(
        "src.linger.agents.serendipity", "skills/connection-discovery/SKILL.md"
    ),
    input_type=ConnectionDiscoveryInput,
    output_type=(ConnectionProposal, ConnectionDecline),
    override_output=False,
    tools=("search_librarian", "search_memories"),
    capabilities=("GuardedExaSearch",),
    validators=("validate_serendipity_output",),
    output_retries=2,
    tool_retries=2,
)

SKILLS = (CONNECTION_DISCOVERY,)
