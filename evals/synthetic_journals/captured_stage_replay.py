"""Inspect saved synthetic stages offline, or explicitly replay one with current Agents."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator
from pydantic_ai.exceptions import (
    ModelAPIError, ModelHTTPError, ModelRetry, UnexpectedModelBehavior, UsageLimitExceeded,
)
from pydantic_core import to_jsonable_python

from apps.backend.config import get_settings
from apps.backend.telemetry import (
    _resolve_effective_model_attrs,
    agent_attrs,
    configure_synthetic_evaluation_telemetry,
)
from src.linger.agents.contracts import PromptFingerprint
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink

from .adoption import validate_ground_truth_adoption_files
from .models import StrictModel
from .transcript import AgentExchange, SceneTranscriptRecorder

ROOT = Path(__file__).resolve().parents[2]
CODE_PATHS = ("src/linger", "apps/backend", "evals/synthetic_journals", "pyproject.toml", "uv.lock")


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class CapturedStageSnapshot(StrictModel):
    """An immutable copy of one original exchange, before current projection."""

    source_path: str
    source_sha256: str
    source_run_id: str
    backstory_sha256: str
    proposed_ground_truth_sha256: str
    dataset_version: str
    scene_id: str
    exchange_json: str
    exchange_sha256: str
    input_sha256: str

    @model_validator(mode="after")
    def verify_hashes(self) -> CapturedStageSnapshot:
        if _sha(self.exchange_json) != self.exchange_sha256:
            raise ValueError("captured exchange does not match its immutable snapshot hash")
        if _sha(self.exchange().input_prompt) != self.input_sha256:
            raise ValueError("captured input does not match its snapshot hash")
        return self

    def exchange(self) -> AgentExchange:
        return AgentExchange.model_validate_json(self.exchange_json)


class StageExecutionIdentity(StrictModel):
    git_head: str
    git_dirty: bool
    git_status_sha256: str
    code_paths: tuple[str, ...]
    code_sha256: str
    configured_model: str
    model: dict[str, Any]
    model_sha256: str


class StageFailure(StrictModel):
    category: Literal[
        "provider_quota", "provider_rate_limit", "provider_http_error", "provider_error",
        "usage_limit", "model_response_error", "contract_validation_error", "unknown_error",
    ]
    error_type: str
    provider_status_code: int | None = None
    provider_code: str | None = None


class StageReplayAttempt(StrictModel):
    repetition: int = Field(ge=1)
    status: Literal["accepted", "failed"]
    elapsed_seconds: float
    output: Any = None
    failure: StageFailure | None = None
    agent_exchanges: tuple[AgentExchange, ...]


class CapturedStageReplayRun(StrictModel):
    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    evaluation_kind: Literal["captured_stage_diagnostic"] = "captured_stage_diagnostic"
    execution_mode: Literal["production", "injected_model"]
    run_id: str
    started_at: str
    snapshot: CapturedStageSnapshot
    execution_identity: StageExecutionIdentity
    execution_identity_after: StageExecutionIdentity
    configuration_unchanged: bool
    current_prompt_fingerprint: PromptFingerprint
    replay_input_sha256: str
    attempts: tuple[StageReplayAttempt, ...]


def _read_source(source: Path) -> tuple[bytes, dict[str, Any]]:
    raw = source.read_bytes()
    document = json.loads(raw)
    if document.get("content_classification") != "synthetic" or document.get("ground_truth_status") != "adopted":
        raise ValueError("captured stage replay requires an adopted synthetic evaluation artifact")
    return raw, document


def load_captured_stage(
    source: Path, *, scene_id: str, sequence: int | None = None,
    role: str | None = None, stage: str | None = None,
) -> CapturedStageSnapshot:
    raw, document = _read_source(source)
    exchanges = [
        AgentExchange.model_validate_json(json.dumps(exchange))
        for scene in document["scenes"] if scene["scene_id"] == scene_id
        for exchange in scene.get("agent_exchanges", ())
        if (sequence is None or exchange["sequence"] == sequence)
        and (role is None or exchange["role"] == role)
        and (stage is None or exchange["stage"] == stage)
    ]
    if len(exchanges) != 1:
        raise ValueError(f"Selector matched {len(exchanges)} exchanges; select one Scene and exchange sequence")
    exchange = exchanges[0]
    frozen = exchange.model_dump_json()
    return CapturedStageSnapshot(
        source_path=str(source.resolve()), source_sha256=_sha(raw),
        source_run_id=document["run_id"], backstory_sha256=document["backstory_sha256"],
        proposed_ground_truth_sha256=document["proposed_ground_truth_sha256"],
        dataset_version=document["dataset_version"], scene_id=scene_id,
        exchange_json=frozen, exchange_sha256=_sha(frozen), input_sha256=_sha(exchange.input_prompt),
    )


def validate_source_adoption(
    snapshot: CapturedStageSnapshot, backstory: Path, ground_truth: Path, adoption: Path,
) -> None:
    """Check the complete adopted scenario outside all evaluated role inputs."""
    story, truth, adopted = validate_ground_truth_adoption_files(backstory, ground_truth, adoption)
    if (
        snapshot.backstory_sha256 != truth.backstory_sha256
        or snapshot.proposed_ground_truth_sha256 != _sha(ground_truth.read_bytes())
        or snapshot.dataset_version != adopted.adopted_ground_truth_identity
        or snapshot.scene_id not in {scene.scene_id for scene in story.scenes}
    ):
        raise ValueError("captured stage and supplied adoption identify different scenario inputs")
    if _sha(Path(snapshot.source_path).read_bytes()) != snapshot.source_sha256:
        raise ValueError("source evaluation artifact changed after capture")
    exchange = snapshot.exchange()
    original = load_captured_stage(
        Path(snapshot.source_path), scene_id=snapshot.scene_id, sequence=exchange.sequence,
        role=exchange.role, stage=exchange.stage,
    )
    if original != snapshot:
        raise ValueError("captured stage does not match the source evaluation artifact")


def execution_identity(agent: Any) -> StageExecutionIdentity:
    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=ROOT, check=True, capture_output=True,
        ).stdout

    head = git("rev-parse", "HEAD").decode().strip()
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    digest = hashlib.sha256(head.encode())
    digest.update(git("diff", "--binary", "HEAD", "--", *CODE_PATHS))
    for name in sorted(git("ls-files", "--others", "--exclude-standard", "-z", "--", *CODE_PATHS).split(b"\0")):
        if name:
            path = ROOT / name.decode()
            digest.update(name + b"\0" + path.read_bytes() + b"\0")
    effective_model, settings = _resolve_effective_model_attrs(agent, {})
    attrs = agent_attrs(
        role="Application", stage="captured_stage", prompt_template_id="captured_stage",
        prompt_digest="", model=effective_model, model_settings=settings,
    )
    model = {key: value for key, value in attrs.items() if key.startswith("model.")}
    configured = get_settings().linger_model
    return StageExecutionIdentity(
        git_head=head, git_dirty=bool(status), git_status_sha256=_sha(status),
        code_paths=CODE_PATHS, code_sha256=digest.hexdigest(), configured_model=configured,
        model=model, model_sha256=_sha(_canonical({"configured": configured, **model})),
    )


def _failure(error: Exception) -> StageFailure:
    category = "unknown_error"
    status, code = None, None
    if isinstance(error, UsageLimitExceeded):
        category = "usage_limit"
    elif isinstance(error, ModelHTTPError):
        status = error.status_code
        category = "provider_http_error"
        body = error.body
        detail = body.get("error", body) if isinstance(body, dict) else {}
        known_codes = {
            "insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached",
            "rate_limit_exceeded", "rate_limit_error", "too_many_requests",
        }
        if isinstance(detail, dict):
            code = next((value for key in ("code", "type")
                         if isinstance(value := detail.get(key), str) and value in known_codes), None)
        if code in {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"}:
            category = "provider_quota"
        elif code in {"rate_limit_exceeded", "rate_limit_error", "too_many_requests"}:
            category = "provider_rate_limit"
    elif isinstance(error, ModelAPIError):
        category = "provider_error"
    elif isinstance(error, (UnexpectedModelBehavior, ModelRetry)):
        category = "model_response_error"
    elif isinstance(error, ValueError):
        category = "contract_validation_error"
    return StageFailure(category=category, error_type=type(error).__name__,
                        provider_status_code=status, provider_code=code)


async def capture_stage_attempts(
    invoke: Callable[[], Awaitable[Any]], *, repetitions: int,
) -> tuple[StageReplayAttempt, ...]:
    """Record repetitions independently, including failed output repair attempts."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    attempts = []
    for repetition in range(1, repetitions + 1):
        recorder = SceneTranscriptRecorder()
        start = monotonic()
        output, failure = None, None
        with bind_evaluation_transcript_sink(recorder):
            try:
                output = to_jsonable_python(await invoke(), serialize_unknown=False)
            except Exception as error:
                failure = _failure(error)
        attempts.append(StageReplayAttempt(
            repetition=repetition, status="failed" if failure else "accepted",
            elapsed_seconds=monotonic() - start, output=output, failure=failure,
            agent_exchanges=recorder.exchanges,
        ))
    return tuple(attempts)


async def replay_captured_stage(
    snapshot: CapturedStageSnapshot, *, backstory: Path, ground_truth: Path,
    adoption: Path, repetitions: int = 1, agent: Any = None,
) -> CapturedStageReplayRun:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    validate_source_adoption(snapshot, backstory, ground_truth, adoption)
    from .captured_stage_tasks import prepare_captured_task
    task = prepare_captured_task(snapshot.exchange(), agent=agent)
    if agent is None:
        from .replay import evaluation_agents
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    identity = execution_identity(task.agent)
    started = datetime.now(timezone.utc).isoformat()
    attempts = await capture_stage_attempts(task.invoke, repetitions=repetitions)
    after = execution_identity(task.agent)
    return CapturedStageReplayRun(
        execution_mode="production" if agent is None else "injected_model",
        run_id=uuid4().hex, started_at=started, snapshot=snapshot,
        execution_identity=identity, current_prompt_fingerprint=task.fingerprint,
        execution_identity_after=after,
        configuration_unchanged=(identity.code_sha256 == after.code_sha256
                                 and identity.model_sha256 == after.model_sha256),
        replay_input_sha256=_sha(task.prompt), attempts=attempts,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    inspect = commands.add_parser("inspect", aliases=["list"], help="List recorded stages without model calls")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--scene")
    run = commands.add_parser("run", help="Make paid model calls for one saved stage")
    run.add_argument("source", type=Path)
    run.add_argument("--scene", required=True)
    run.add_argument("--sequence", type=int)
    run.add_argument("--role")
    run.add_argument("--stage")
    run.add_argument("--backstory", type=Path, required=True)
    run.add_argument("--ground-truth", type=Path, required=True)
    run.add_argument("--adoption", type=Path, required=True)
    run.add_argument("--repetitions", type=int, default=1)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.operation in {"inspect", "list"}:
        from .captured_stage_tasks import SUPPORTED_STAGES
        _, document = _read_source(args.source)
        for scene in document["scenes"]:
            if args.scene is not None and scene["scene_id"] != args.scene:
                continue
            for exchange in scene.get("agent_exchanges", ()):
                print(_canonical({
                    "scene_id": scene["scene_id"], "sequence": exchange["sequence"],
                    "role": exchange["role"], "stage": exchange["stage"],
                    "status": exchange["status"],
                    "supported": (exchange["role"], exchange["stage"]) in SUPPORTED_STAGES,
                }))
        return 0
    snapshot = load_captured_stage(
        args.source, scene_id=args.scene, sequence=args.sequence, role=args.role, stage=args.stage,
    )
    if args.output.resolve() in {
        path.resolve() for path in (args.source, args.backstory, args.ground_truth, args.adoption)
    }:
        raise ValueError("replay output must not overwrite a source or adoption file")
    if args.output.exists():
        raise ValueError("replay output already exists; choose a new artifact path")
    result = asyncio.run(replay_captured_stage(
        snapshot, backstory=args.backstory, ground_truth=args.ground_truth,
        adoption=args.adoption, repetitions=args.repetitions,
    ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        target.write(result.model_dump_json(indent=2) + "\n")
    print(f"CAPTURED_STAGE_REPLAY_OUTPUT={args.output}")
    return int(any(attempt.failure is not None for attempt in result.attempts))


if __name__ == "__main__":
    raise SystemExit(main())
