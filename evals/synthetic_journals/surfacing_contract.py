"""Compile isolated proactive Scenes from authorised, active source records."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from evals.sculptor.surfacing_harness import CASE_DECISIONS, SurfacingExpectation
from evals.synthetic_journals.models import (
    PropEvidence,
    ProposedGroundTruth,
    SyntheticBackstory,
)
from src.linger.agents.sculptor.models import CuratableMemory
from src.linger.agents.sculptor.surfacing_models import AtTime, SurfacingInput

SURFACING_OBJECTIVE_ID = "proactive_memory_surfacing"


class SurfacingContractError(ValueError):
    """A package cannot establish the standalone surfacing evaluation."""


@dataclass(frozen=True)
class CompiledSurfacingScene:
    scene_id: str
    order: int
    input: SurfacingInput
    expectation: SurfacingExpectation


def compile_surfacing_scenes(
    backstory: SyntheticBackstory, ground_truth: ProposedGroundTruth
) -> tuple[CompiledSurfacingScene, ...]:
    """Resolve one bounded snapshot per Scene; keep answer keys out of inputs."""
    try:
        backstory = SyntheticBackstory.model_validate_json(backstory.model_dump_json())
        ground_truth = ProposedGroundTruth.model_validate_json(ground_truth.model_dump_json())
    except ValidationError as error:
        raise SurfacingContractError("invalid surfacing package graph") from error
    if set(backstory.objective_ids) != {SURFACING_OBJECTIVE_ID}:
        raise SurfacingContractError("surfacing replay requires its sole Objective")
    props = {item.prop_id: item for item in backstory.props}
    offline = {item.offline_input_id: item for item in backstory.offline_inputs}
    proposals = {item.scene_id: item for item in ground_truth.proposals}
    if (
        set(proposals) != {scene.scene_id for scene in backstory.scenes}
        or len(proposals) != len(ground_truth.proposals)
        or any(p.objective_id != SURFACING_OBJECTIVE_ID for p in ground_truth.proposals)
    ):
        raise SurfacingContractError("surfacing requires one proposal per Scene")
    compiled: list[CompiledSurfacingScene] = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if scene.line_ids or len(scene.offline_input_ids) != 1:
            raise SurfacingContractError(
                f"{scene.scene_id}: requires one OfflineInput and no Lines"
            )
        if not scene.fresh_session:
            raise SurfacingContractError("surfacing Scenes use explicit fresh snapshots")
        item = offline[scene.offline_input_ids[0]]
        if item.kind != SURFACING_OBJECTIVE_ID or item.surfacing_context is None:
            raise SurfacingContractError(f"{scene.scene_id}: missing surfacing context")
        if set(item.prop_ids) != set(scene.prop_ids):
            raise SurfacingContractError("offline Props must equal the Scene candidate bank")
        active_ids = tuple(
            prop_id for prop_id in item.prop_ids
            if any(
                state.scene_id == scene.scene_id and state.state == "active"
                for state in props[prop_id].lifecycle
            )
        )
        try:
            input = SurfacingInput(
                account_scope=backstory.backstory.evaluation_account_id,
                context=item.surfacing_context,
                memories=tuple(
                    CuratableMemory(memory_id=prop_id, text=props[prop_id].source_text)
                    for prop_id in active_ids
                ),
            )
        except ValidationError as error:
            raise SurfacingContractError(f"{scene.scene_id}: invalid bounded input") from error
        proposal = proposals[scene.scene_id]
        expected = proposal.surfacing
        if expected is None:
            raise SurfacingContractError(f"{scene.scene_id}: missing surfacing expectation")
        if not set(expected.allowed_source_ids) <= set(active_ids):
            raise SurfacingContractError("expected sources must be active input Props")
        evidence_ids = {
            evidence.prop_id for evidence in proposal.evidence
            if isinstance(evidence, PropEvidence)
        }
        exact_ids = {
            span.source_id for span in proposal.exact_spans
            if span.source_kind == "prop" and span.source_id in props
            and props[span.source_id].source_text[
                span.start_codepoint:span.end_codepoint
            ] == span.text
        }
        if not set(expected.allowed_source_ids) <= evidence_ids & exact_ids:
            raise SurfacingContractError("allowed sources require Prop evidence and exact spans")
        if isinstance(expected.reconsideration, AtTime):
            if expected.reconsideration.at <= input.context.now:
                raise SurfacingContractError("expected reconsideration must be after now")
        if expected.case_kind == "repeated" and not input.context.history:
            raise SurfacingContractError("repeated cases require prior surfacing history")
        compiled.append(CompiledSurfacingScene(scene.scene_id, scene.order, input, expected))

    kinds = {item.expectation.case_kind for item in compiled}
    if kinds != set(CASE_DECISIONS):
        raise SurfacingContractError(
            "surfacing package must cover timely, deferred, superseded, repeated, "
            "unsupported and sensitive cases"
        )
    _require_temporal_pair(compiled, ground_truth)
    return tuple(compiled)


def _require_temporal_pair(
    scenes: list[CompiledSurfacingScene], ground_truth: ProposedGroundTruth
) -> None:
    by_id = {scene.scene_id: scene for scene in scenes}
    for proposal in ground_truth.proposals:
        if proposal.pairing is None:
            continue
        current = by_id[proposal.scene_id]
        paired = by_id.get(proposal.pairing.paired_scene_id)
        if paired is None:
            continue
        if {current.expectation.case_kind, paired.expectation.case_kind} != {
            "timely", "deferred"
        }:
            continue
        early, late = (
            (current, paired) if current.expectation.case_kind == "deferred"
            else (paired, current)
        )
        if (
            early.input.context.now < late.input.context.now
            and early.input.model_dump(exclude={"context": {"now"}})
            == late.input.model_dump(exclude={"context": {"now"}})
        ):
            return
    raise SurfacingContractError(
        "surfacing requires a declared timely/deferred pair differing only in decision time"
    )
