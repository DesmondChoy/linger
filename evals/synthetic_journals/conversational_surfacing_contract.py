"""Compile the versioned ordered contract for 4.2.5 conversation replay."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from evals.synthetic_journals.models import (
    ConversationalCaptureExpectation,
    ConversationalSceneExpectation,
    ConversationalSceneSpec,
    ConversationalSurfacingExpectation,
    GroundTruthProposal,
    Line,
    Prop,
    ProposedGroundTruth,
    Scene,
    SyntheticBackstory,
)

CONVERSATIONAL_CONTRACT = "conversational_v1"
CONVERSATIONAL_OBJECTIVE_ID = "proactive_memory_surfacing"


class ConversationalContractError(ValueError):
    """A scenario cannot establish the ordered conversational evaluation."""


@dataclass(frozen=True)
class CompiledConversationalScene:
    scene: Scene
    workflow: ConversationalSceneSpec
    line: Line
    expectation: ConversationalSceneExpectation


def compile_conversational_scenes(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> tuple[CompiledConversationalScene, ...]:
    """Resolve ordered Lines and symbolic answer-key dependencies."""

    try:
        backstory = SyntheticBackstory.model_validate_json(
            backstory.model_dump_json()
        )
        ground_truth = ProposedGroundTruth.model_validate_json(
            ground_truth.model_dump_json()
        )
    except ValidationError as error:
        raise ConversationalContractError("invalid conversational scenario graph") from error

    if backstory.scenario_contract != CONVERSATIONAL_CONTRACT:
        raise ConversationalContractError("backstory does not select conversational_v1")
    if ground_truth.scenario_contract != CONVERSATIONAL_CONTRACT:
        raise ConversationalContractError(
            "Ground truth does not select conversational_v1"
        )
    if set(backstory.objective_ids) != {CONVERSATIONAL_OBJECTIVE_ID}:
        raise ConversationalContractError(
            "conversational replay requires its sole Objective"
        )

    scenes = {scene.scene_id: scene for scene in backstory.scenes}
    workflows = {
        item.scene_id: item for item in backstory.conversational_scenes
    }
    lines = {line.line_id: line for line in backstory.lines}
    proposals = {proposal.scene_id: proposal for proposal in ground_truth.proposals}
    if set(workflows) != set(scenes):
        raise ConversationalContractError(
            "conversational_v1 requires one workflow spec per Scene"
        )
    if set(proposals) != set(scenes) or len(proposals) != len(ground_truth.proposals):
        raise ConversationalContractError(
            "conversational_v1 requires one proposal per Scene"
        )

    compiled: list[CompiledConversationalScene] = []
    seen_capture = False
    seen_surfacing = False
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        workflow = workflows[scene.scene_id]
        line_ids = tuple(scene.line_ids)
        if len(line_ids) != 1 or scene.offline_input_ids:
            raise ConversationalContractError(
                f"{scene.scene_id}: requires exactly one Line and no OfflineInput"
            )
        line = lines[line_ids[0]]
        if line.scene_id != scene.scene_id:
            raise ConversationalContractError(
                f"{scene.scene_id}: Line belongs to another Scene"
            )
        if any(
            prerequisite not in scenes
            or scenes[prerequisite].order >= scene.order
            for prerequisite in workflow.prerequisite_scene_ids
        ):
            raise ConversationalContractError(
                f"{scene.scene_id}: prerequisites must be earlier Scenes"
            )
        proposal = proposals[scene.scene_id]
        expectation = proposal.conversational
        if expectation is None:
            raise ConversationalContractError(
                f"{scene.scene_id}: missing conversational expectation"
            )
        if expectation.kind != workflow.kind:
            raise ConversationalContractError(
                f"{scene.scene_id}: workflow and Ground truth kinds differ"
            )
        if workflow.kind == "capture":
            seen_capture = True
            if scene.fresh_session is not True:
                raise ConversationalContractError(
                    f"{scene.scene_id}: capture Scene must start a fresh session"
                )
            _validate_capture_expectation(expectation, scene, backstory.props)
        else:
            seen_surfacing = True
            if scene.fresh_session is not True:
                raise ConversationalContractError(
                    f"{scene.scene_id}: surfacing Scene must start a fresh session"
                )
            if not workflow.prerequisite_scene_ids:
                raise ConversationalContractError(
                    f"{scene.scene_id}: surfacing Scene needs a prerequisite capture"
                )
    if not seen_capture or not seen_surfacing:
        raise ConversationalContractError(
            "conversational_v1 requires capture and surfacing Scenes"
        )
    return tuple(
        CompiledConversationalScene(
            scene=scene,
            workflow=workflows[scene.scene_id],
            line=lines[scene.line_ids[0]],
            expectation=proposals[scene.scene_id].conversational,
        )
        for scene in sorted(backstory.scenes, key=lambda item: item.order)
    )


def _validate_capture_expectation(
    expectation: ConversationalCaptureExpectation,
    scene: Scene,
    props: tuple[Prop, ...],
) -> None:
    prop_ids = {prop.prop_id for prop in props}
    scene_prop_ids = set(scene.prop_ids)
    for reference in expectation.curation_source_references:
        if reference.kind == "source_prop" and reference.reference not in prop_ids:
            raise ConversationalContractError(
                f"{scene.scene_id}: curation references unknown source Prop"
            )
        if reference.kind == "source_prop" and reference.reference not in scene_prop_ids:
            raise ConversationalContractError(
                f"{scene.scene_id}: curation references an unassigned source Prop"
            )
