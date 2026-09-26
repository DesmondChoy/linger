"""Compare Muse authoring formats after a captured, fixed retrieval result.

The same original turn envelope is repeated after the saved tool results so
current output validation receives its typed prompt. No new tools are exposed.
This is a projected diagnostic, not a full turn or a scenario pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from pydantic import TypeAdapter
from pydantic_ai import ToolOutput, UsageLimits
from pydantic_ai.messages import ModelMessagesTypeAdapter

from apps.backend.contracts import EvidenceItem, MuseDraftInput, MuseRevisionInput
from apps.backend.telemetry import run_agent_traced
from src.linger.agents.muse.skills import REFLECTION
from src.linger.contracts.connection_evidence import (
    ConnectionSourceEvidence, WebConnectionEvidence, wrap_untrusted_web_excerpt,
)
from src.linger.contracts.librarian import EvidenceRecord
from src.linger.orchestration.book_evidence import evidence_record_from_item
from src.linger.orchestration.inspection_context import (
    begin_connection_inspection, register_connection_evidence, reset_connection_inspection,
)
from src.linger.orchestration.turn_context import (
    ToolExposure, reset_connection_book_scopes, reset_reader_message,
    reset_tool_exposure, reset_turn_evidence, set_connection_book_scopes,
    set_reader_message, set_tool_exposure, set_turn_evidence,
)

from .captured_stage_replay import CapturedStageSnapshot
from .muse_composition import COMPOSITION_INSTRUCTIONS, MuseComposition, compose_muse_output

_MUSE_INPUT = TypeAdapter(MuseDraftInput | MuseRevisionInput)
_CONNECTION_SOURCE = TypeAdapter(ConnectionSourceEvidence)


def authoring_skill(*, composition: bool):
    if not composition:
        return replace(REFLECTION, tools=())
    return replace(
        REFLECTION, name="reflection-composition-experiment", tools=(),
        instructions=f"{REFLECTION.instructions}\n\n{COMPOSITION_INSTRUCTIONS}",
        output_type=MuseComposition, override_output=True, output_validator=compose_muse_output,
        validators=("compile_composition", "validate_muse_output"),
    )


def history_before_first_output(exchange: Any) -> list[dict]:
    """Keep retrieval and earlier turns; exclude this invocation's failed output."""
    messages = list(exchange.model_messages)
    if not exchange.model_messages_include_history:
        messages = [*exchange.message_history, *messages]
    input_index = next((index for index, message in enumerate(messages) if any(
        part.get("part_kind") == "user-prompt" and part.get("content") == exchange.input_prompt
        for part in message["parts"]
    )), None)
    if input_index is None:
        raise ValueError("captured Muse invocation has no matching input envelope")
    for index in range(input_index + 1, len(messages)):
        if any(part.get("part_kind") == "tool-call" and part.get("tool_name") == "final_result"
               for part in messages[index]["parts"]):
            return messages[:index]
    raise ValueError("captured Muse invocation has no output boundary")


def book_record_from_tool(tool_name: str, source: dict) -> EvidenceRecord | None:
    if tool_name == "librarian_search":
        return EvidenceRecord.model_validate(source)
    if tool_name == "serendipity_explore" and source.get("source_kind") == "book_corpus":
        return evidence_record_from_item(EvidenceItem.model_validate(source))
    return None


@dataclass(frozen=True)
class CapturedMuseTask:
    prompt: str
    history_json: str
    book_records: tuple[EvidenceRecord, ...]
    connection_records: tuple[ConnectionSourceEvidence, ...]
    stage: str
    agent: Any

    async def invoke(self, *, composition: bool = False) -> Any:
        task = _MUSE_INPUT.validate_json(self.prompt)
        history = ModelMessagesTypeAdapter.validate_json(self.history_json)
        books_token = set_turn_evidence(self.book_records)
        inspection_token = begin_connection_inspection()
        exposure_token = set_tool_exposure(ToolExposure(frozenset()))
        reader_token = set_reader_message(task.muse_turn.user_message)
        scopes_token = set_connection_book_scopes(task.muse_turn.connection_book_scopes)
        try:
            register_connection_evidence(self.connection_records)
            skill = authoring_skill(composition=composition)
            options = skill.run_options()
            if composition:
                options["output_type"] = ToolOutput(compose_muse_output, name="final_result")
            fingerprint = skill.fingerprint()
            result = await run_agent_traced(
                self.agent, self.prompt, span_name="captured_stage.muse.post_retrieval",
                role="Muse", stage=self.stage,
                input_contract=f"{type(task).__module__}.{type(task).__name__}",
                output_contract="src.linger.agents.muse.models.MuseCandidate",
                prompt_template_id=fingerprint.template_id, prompt_digest=fingerprint.digest,
                failure_code="captured_muse_failed", message_history=history,
                usage_limits=UsageLimits(request_limit=REFLECTION.output_retries + 1),
                **options,
            )
            return result.output
        finally:
            reset_connection_book_scopes(scopes_token)
            reset_reader_message(reader_token)
            reset_tool_exposure(exposure_token)
            reset_connection_inspection(inspection_token)
            reset_turn_evidence(books_token)


def prepare_muse_task(snapshot: CapturedStageSnapshot, *, agent: Any = None) -> CapturedMuseTask:
    exchange = snapshot.exchange()
    if exchange.role != "Muse" or exchange.stage not in {"draft", "revision"}:
        raise ValueError("expected one Muse draft or revision exchange")
    history = history_before_first_output(exchange)
    task = _MUSE_INPUT.validate_json(exchange.input_prompt)
    # Evidence events supply canonical raw text. Only records actually visible
    # in the captured input/tool results can enter this replay's source ledgers.
    from pathlib import Path
    from .captured_stage_replay import _sha
    raw = Path(snapshot.source_path).read_bytes()
    if _sha(raw) != snapshot.source_sha256:
        raise ValueError("captured source changed")
    scene = next(scene for scene in json.loads(raw)["scenes"] if scene["scene_id"] == snapshot.scene_id)
    canonical: dict[str, ConnectionSourceEvidence] = {}
    for event in scene.get("events", ()):
        for encoded in event.get("evidence_json", ()):
            source = json.loads(encoded)
            if source.get("source_kind") in {"web", "memory"}:
                record = _CONNECTION_SOURCE.validate_python(source)
                if record.evidence_id in canonical and canonical[record.evidence_id] != record:
                    raise ValueError("captured evidence ID has conflicting canonical records")
                canonical[record.evidence_id] = record

    books: dict[str, EvidenceRecord] = {}
    connections: dict[str, ConnectionSourceEvidence] = {}

    def add_book(record: EvidenceRecord) -> None:
        if record.evidence_id in books and books[record.evidence_id] != record:
            raise ValueError("captured book evidence ID has conflicting records")
        books[record.evidence_id] = record

    def add_source(source: dict) -> None:
        visible = _CONNECTION_SOURCE.validate_python(source)
        record = canonical.get(visible.evidence_id)
        if record is None:
            raise ValueError("visible source is absent from canonical evaluation events")
        expected = record
        if isinstance(record, WebConnectionEvidence):
            expected = record.model_copy(update={"excerpt": wrap_untrusted_web_excerpt(record.excerpt)})
        if visible != expected and visible != record:
            raise ValueError("visible source does not match the canonical record")
        connections[record.evidence_id] = record

    for message in history:
        for part in message["parts"]:
            if part.get("part_kind") == "user-prompt" and isinstance(part.get("content"), str):
                try:
                    envelope = _MUSE_INPUT.validate_json(part["content"])
                except ValueError:
                    continue
                for record in envelope.prior_evidence:
                    add_book(record)
                surfacing = getattr(envelope, "memory_surfacing", None)
                if surfacing is not None:
                    for source in surfacing.sources:
                        add_source(source.model_dump(mode="json"))
            if part.get("part_kind") == "tool-return" and part.get("tool_name") in {
                "librarian_search", "serendipity_explore",
            }:
                payload = part.get("content")
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if not isinstance(payload, dict):
                    raise ValueError("unsupported captured retrieval payload")
                for source in payload.get("evidence", ()):
                    book = book_record_from_tool(part["tool_name"], source)
                    if book is not None:
                        add_book(book)
                    elif source.get("source_kind") in {"web", "memory"}:
                        add_source(source)
    if agent is None:
        from src.linger.agents.muse.agent import muse_chat_agent
        agent = muse_chat_agent
    return CapturedMuseTask(
        prompt=task.model_dump_json(), history_json=json.dumps(history),
        book_records=tuple(books.values()), connection_records=tuple(connections.values()),
        stage=exchange.stage, agent=agent,
    )
