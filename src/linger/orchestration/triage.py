"""Application-owned invocation of Muse's turn triage."""

import json
from typing import Any

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models import Model

from apps.backend.telemetry import run_agent_traced
from src.linger.agents.muse.prompt import TURN_TRIAGE_PROMPT_FINGERPRINT
from src.linger.agents.muse.skills import REFLECTION, TURN_TRIAGE
from src.linger.contracts.triage import TurnNeeds, TurnTriageInput
from src.linger.orchestration.turn_context import ToolExposure

BOOK_TOOLS = frozenset({"librarian_route", "librarian_search"})
# No tools reach turn triage; this bounds its own structured-output repair
# attempts. A model that answers with calls to tools it was never given would
# otherwise keep earning fresh retry prompts.
TURN_TRIAGE_REQUEST_LIMIT = TURN_TRIAGE.output_retries + 1
# `none` adds nothing and `unsure` adds the tool without pinning an intent.
PINNED_INTENTS = {
    "own_earlier_reflections": "recall_memory",
    "named_sources": "gather_sources",
    "source_comparison": "find_connection",
    "outside_recommendation": "get_recommendation",
}


def expose_tools(
    needs: TurnNeeds | None,
    *,
    previously_called: frozenset[str],
    book_override: bool,
) -> ToolExposure:
    """Add this turn's needs to the session's earlier tools; a failed triage adds book tools only."""
    tools = set(previously_called) & set(REFLECTION.tools)
    if needs is None:
        # Nothing was classified, so add only the book tools, which reach
        # neither the web nor the account's memories. `serendipity_explore`
        # stays out unless an earlier released turn already used it. The
        # override signal is `unknown`, not a confirmed clean turn, since
        # triage never ran to completion.
        return ToolExposure(tools=frozenset(tools | BOOK_TOOLS), override_attempt="unknown")
    if needs.override_attempt == "attempted":
        # Least privilege: grant nothing this message's claimed needs unlock.
        if book_override:
            tools |= BOOK_TOOLS
        return ToolExposure(tools=frozenset(tools), override_attempt="attempted")
    if book_override or needs.book_content != "no":
        tools |= BOOK_TOOLS
    if needs.memory != "none":
        tools.add("serendipity_explore")
    return ToolExposure(
        tools=frozenset(tools), pinned_intent=PINNED_INTENTS.get(needs.memory)
    )


async def triage_turn(
    current_line: str,
    *,
    muse: Agent[None, Any],
    model: Model | None = None,
) -> TurnNeeds:
    """Classify what one reader message needs, from that message alone."""
    triage_input = TurnTriageInput(current_line=current_line)
    run_options = TURN_TRIAGE.run_options()
    if model is not None:
        run_options["model"] = model
    result = await run_agent_traced(
        muse,
        json.dumps(triage_input.model_dump(mode="json"), ensure_ascii=False),
        span_name="muse.turn_triage",
        role="Muse",
        stage="turn_triage",
        input_contract="src.linger.contracts.triage.TurnTriageInput",
        output_contract="src.linger.contracts.triage.TurnNeeds",
        prompt_template_id=TURN_TRIAGE_PROMPT_FINGERPRINT.template_id,
        prompt_digest=TURN_TRIAGE_PROMPT_FINGERPRINT.digest,
        failure_code="turn_triage_failed",
        result_attrs=lambda run_result: {
            "triage.book_content": run_result.output.book_content,
            "triage.memory": run_result.output.memory,
            "triage.override_attempt": run_result.output.override_attempt,
        },
        usage_limits=UsageLimits(request_limit=TURN_TRIAGE_REQUEST_LIMIT),
        **run_options,
    )
    return TurnNeeds.model_validate(result.output)
