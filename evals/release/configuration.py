"""Read the selected runtime's effective model configuration without inference."""

import json
from typing import Any

from apps.backend.telemetry import (
    _model_identity, _model_settings_attr, _resolve_effective_model_attrs,
)


def model_configuration(agent: Any, run_options: dict[str, Any] | None = None) -> dict[str, Any]:
    model, settings = _resolve_effective_model_attrs(agent, run_options or {})
    if model is None:
        raise ValueError("Effective model configuration could not be resolved.")
    provider, name = _model_identity(model)
    safe_settings = _model_settings_attr(settings)
    return {
        "provider": provider,
        "model": name,
        "settings": json.loads(safe_settings) if safe_settings else {},
    }


def runtime_configuration() -> dict[str, Any]:
    from apps.backend.chat_turn import muse_chat_agent, triage_model
    from evals.synthetic_journals.replay import evaluation_agents
    from src.linger.agents.muse.skills import TURN_TRIAGE

    roles = {agent.name: model_configuration(agent) for agent in evaluation_agents()}
    roles["Muse.turn_triage"] = model_configuration(
        muse_chat_agent, {**TURN_TRIAGE.run_options(), "model": triage_model},
    )
    return {"roles": roles, "unspecified_settings": "provider defaults"}


if __name__ == "__main__":
    print(json.dumps(runtime_configuration(), sort_keys=True))
