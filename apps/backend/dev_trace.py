"""Developer-only content trace for one live turn, shown in Inspect.

Bound only when `LINGER_DEV_INSPECT` is on. It reuses the evaluation transcript
hooks, which record without changing agent behaviour, and keeps everything in
memory for the one response. Nothing here reaches Logfire or storage beyond
the account's own saved turn.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from itertools import count
from typing import Any

from pydantic_core import to_jsonable_python

from src.linger.evaluation_transcript import ConnectionEvaluationEvent

# Parts that add nothing beyond the recorded prompt: instructions and the prompt itself.
_SKIPPED_PARTS = {"system-prompt", "user-prompt"}


def _json(value: Any) -> Any:
    return to_jsonable_python(value, fallback=repr)


def _steps(messages: Sequence[Any]) -> list[dict[str, Any]]:
    """Tool calls, tool results, retries and text an agent produced during its run."""
    steps = []
    for message in messages:
        for part in getattr(message, "parts", ()):
            kind = getattr(part, "part_kind", None)
            if kind is None or kind in _SKIPPED_PARTS:
                continue
            step: dict[str, Any] = {"kind": kind}
            if getattr(part, "tool_name", None):
                step["tool"] = part.tool_name
            if kind == "tool-call":
                step["args"] = _json(part.args)
            elif hasattr(part, "content"):
                step["content"] = _json(part.content)
            steps.append(step)
    return steps


class DevTraceSink:
    """Collects agent exchanges and connection events in invocation order."""

    def __init__(self) -> None:
        self._order = count()
        self._exchanges: dict[int, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []

    def begin_agent_exchange(self, *, role: str, stage: str, input_prompt: str,
                             skill_id: str | None = None, **_: Any) -> int:
        handle = next(self._order)
        self._exchanges[handle] = {
            "role": role, "stage": stage, "skill": skill_id,
            "input_prompt": input_prompt, "status": "running",
        }
        return handle

    def complete_agent_exchange(self, handle: object, *, result: Any | None, status: str,
                                failure_code: str | None, partial_messages: Sequence[Any] = (),
                                **_: Any) -> None:
        exchange = self._exchanges[handle]  # type: ignore[index]
        messages = result.new_messages() if result is not None else partial_messages
        exchange.update(
            status=status,
            failure_code=failure_code,
            steps=_steps(messages),
            output=_json(result.output) if result is not None else None,
        )

    def record_connection_event(self, event: ConnectionEvaluationEvent) -> None:
        fields = {key: value for key, value in asdict(event).items() if value not in (None, (), "")}
        # Evidence and decisions arrive as JSON text; parse them so Inspect shows structure.
        if "evidence_json" in fields:
            fields["evidence"] = [json.loads(item) for item in fields.pop("evidence_json")]
        if "decision_json" in fields:
            fields["decision"] = json.loads(fields.pop("decision_json"))
        self._events.append(fields)

    def payload(self) -> dict[str, Any]:
        return {
            "agent_exchanges": [self._exchanges[key] for key in sorted(self._exchanges)],
            "connection_events": self._events,
        }
