"""Replay capture-only Scenes through Linger's production chat boundary."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from apps.backend import sessions
from apps.backend.schemas import CaptureInspection, ChatRequest, ChatResponse
from src.linger.services.memory import AccountContext, MemoryPolicyService

from .models import StrictModel, SyntheticContent
from .validate_package import PackageValidationError, validate_package_files

CAPTURE_OBJECTIVE_ID = "reviewed_automatic_memory_capture"

ChatHandler = Callable[
    [ChatRequest, MemoryPolicyService, AccountContext],
    Awaitable[ChatResponse],
]


class SceneObservation(StrictModel):
    """Recorded production outcome for one Scene and its single Line."""

    scene_id: str
    line_id: str
    session_id: str
    turn_id: str
    reply: str
    release_source: Literal["muse_candidate", "application_safe_decline"]
    capture: CaptureInspection
    memory_id: str | None
    stored_text: str | None


class EvaluationRun(StrictModel):
    """One isolated run of ordered capture-only Scenes."""

    run_id: str
    objective_id: Literal["reviewed_automatic_memory_capture"]
    evaluation_account_id: str
    capture_enabled: Literal[True]
    scenes: tuple[SceneObservation, ...]
    final_active_memory_ids: tuple[str, ...]


async def replay_capture_scenes(
    content: SyntheticContent,
    *,
    chat_handler: ChatHandler | None = None,
) -> EvaluationRun:
    """Run one Line per Scene with isolated storage and server-owned policy."""

    scene_lines = _capture_scene_lines(content)
    handler = chat_handler or _production_chat
    run_id = uuid4().hex
    account = AccountContext(
        f"synthetic-eval:{content.backstory.evaluation_account_id}:{run_id}"
    )
    observations: list[SceneObservation] = []

    with tempfile.TemporaryDirectory(prefix="linger-synthetic-eval-") as directory:
        service = MemoryPolicyService(Path(directory))
        if service.capture_enabled(
            account
        ):  # pragma: no cover - fresh store invariant
            raise RuntimeError(
                "isolated evaluation account unexpectedly has capture enabled"
            )
        service.set_capture_enabled(account, True)

        for scene_id, line_id, line_text in scene_lines:
            session_id = f"synthetic-eval:{run_id}:session:{uuid4().hex}"
            turn_id = f"synthetic-eval:{run_id}:turn:{uuid4().hex}"
            request = ChatRequest(
                session_id=session_id,
                turn_id=turn_id,
                message=line_text,
            )
            try:
                response = await handler(request, service, account)
            finally:
                sessions.clear(session_id)

            release = response.inspection.release
            if release is None:
                raise RuntimeError(
                    "production chat returned no release inspection for Scene "
                    f"{scene_id}"
                )
            matching_records = tuple(
                record
                for record in service.list_active(account)
                if record.source_event_id == turn_id
            )
            if len(matching_records) > 1:  # pragma: no cover - service invariant
                raise RuntimeError(f"Scene {scene_id} created multiple memories")
            record = matching_records[0] if matching_records else None
            committed = release.capture.storage == "committed"
            if committed != (record is not None):
                raise RuntimeError(
                    f"Scene {scene_id} capture inspection disagrees with storage"
                )
            observations.append(
                SceneObservation(
                    scene_id=scene_id,
                    line_id=line_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    reply=response.reply,
                    release_source=release.release_source,
                    capture=release.capture,
                    memory_id=record.memory_id if record else None,
                    stored_text=record.text if record else None,
                )
            )

        active_ids = tuple(
            record.memory_id for record in service.list_active(account)
        )

    return EvaluationRun(
        run_id=run_id,
        objective_id=CAPTURE_OBJECTIVE_ID,
        evaluation_account_id=account.account_id,
        capture_enabled=True,
        scenes=tuple(observations),
        final_active_memory_ids=active_ids,
    )


def _capture_scene_lines(
    content: SyntheticContent,
) -> tuple[tuple[str, str, str], ...]:
    if content.objective_ids != (CAPTURE_OBJECTIVE_ID,):
        raise ValueError(
            "capture replay requires only reviewed_automatic_memory_capture"
        )
    if content.props or content.offline_inputs:
        raise ValueError("capture replay does not accept Props or offline inputs")

    lines = {line.line_id: line for line in content.lines}
    scene_lines: list[tuple[str, str, str]] = []
    for scene in sorted(content.scenes, key=lambda item: item.order):
        if not scene.fresh_session:
            raise ValueError(f"Scene {scene.scene_id} must use a fresh session")
        if scene.prop_ids or scene.offline_input_ids:
            raise ValueError(
                f"Scene {scene.scene_id} cannot use Props or offline inputs"
            )
        if len(scene.line_ids) != 1:
            raise ValueError(f"Scene {scene.scene_id} must contain exactly one Line")
        line_id = scene.line_ids[0]
        line = lines[line_id]
        if line.order != 1:
            raise ValueError(f"Scene {scene.scene_id} Line must have order 1")
        scene_lines.append((scene.scene_id, line_id, line.text))
    return tuple(scene_lines)


async def _production_chat(
    request: ChatRequest,
    service: MemoryPolicyService,
    account: AccountContext,
) -> ChatResponse:
    from apps.backend.main import chat
    from fastapi import HTTPException

    try:
        return await chat(request, service, account)
    except HTTPException as error:
        raise RuntimeError(f"production chat failed: {error.detail}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("authoring_manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        content, _ = validate_package_files(args.content, args.authoring_manifest)
        result = asyncio.run(replay_capture_scenes(content))
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, PackageValidationError, RuntimeError, ValueError) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
