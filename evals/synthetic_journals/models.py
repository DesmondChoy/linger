"""Strict Backstory and Ground truth contracts for synthetic evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from evals.reflection.harness import GroundingExpectation
from evals.sculptor.harness import CurationExpectation


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must contain a non-whitespace character")
    return value

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        pattern=r"^[^\s]+$",
    ),
]
Text = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_reject_blank),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _require_unique(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")


class StrictModel(BaseModel):
    """Reject coercion, mutation, and unrecognized fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Backstory(StrictModel):
    """One generator-only history for one person and evaluation account."""

    backstory_id: Identifier
    person_id: Identifier
    evaluation_account_id: Identifier
    context: Text


class PropLifecycle(StrictModel):
    """Trusted workflow state for one Prop before one Scene runs."""

    scene_id: Identifier
    state: Literal["active", "inactive", "superseded", "deleted"]


class Prop(StrictModel):
    """A separate source record positioned before designated Scenes."""

    prop_id: Identifier
    backstory_id: Identifier
    person_id: Identifier
    evaluation_account_id: Identifier
    source_text: Text
    lifecycle: tuple[PropLifecycle, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        _require_unique(
            "Prop lifecycle scene IDs",
            tuple(item.scene_id for item in self.lifecycle),
        )
        return self


class Line(StrictModel):
    """One ordered user input sent through the production chat boundary."""

    line_id: Identifier
    scene_id: Identifier
    order: int = Field(ge=1)
    text: Text


class OfflineInput(StrictModel):
    """A generated non-Line input for an offline or evidence-driven Scene."""

    offline_input_id: Identifier
    scene_id: Identifier
    order: int = Field(ge=1)
    kind: Identifier
    text: Text | None = None
    prop_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        _require_unique("OfflineInput prop_ids", self.prop_ids)
        if self.text is None and not self.prop_ids:
            raise ValueError("OfflineInput requires text or at least one Prop")
        return self


class Scene(StrictModel):
    """One bounded evaluation unit in a fresh or continued session."""

    scene_id: Identifier
    backstory_id: Identifier
    objective_ids: tuple[Identifier, ...] = Field(min_length=1)
    order: int = Field(ge=1)
    fresh_session: bool
    prop_ids: tuple[Identifier, ...] = ()
    line_ids: tuple[Identifier, ...] = ()
    offline_input_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _require_unique("Scene objective_ids", self.objective_ids)
        _require_unique("Scene prop_ids", self.prop_ids)
        _require_unique("Scene line_ids", self.line_ids)
        _require_unique("Scene offline_input_ids", self.offline_input_ids)
        if not (self.prop_ids or self.line_ids or self.offline_input_ids):
            raise ValueError("Scene requires at least one Prop, Line, or OfflineInput")
        return self


class SyntheticBackstory(StrictModel):
    """Generated package rooted in one Backstory, person, and account."""

    objective_ids: tuple[Identifier, ...] = Field(min_length=1)
    run_configuration_ids: tuple[Identifier, ...] = ()
    backstory: Backstory
    props: tuple[Prop, ...] = ()
    scenes: tuple[Scene, ...] = Field(min_length=1)
    lines: tuple[Line, ...] = ()
    offline_inputs: tuple[OfflineInput, ...] = ()

    @model_validator(mode="after")
    def validate_backstory_graph(self) -> Self:
        _require_unique("Backstory objective_ids", self.objective_ids)
        _require_unique("run_configuration_ids", self.run_configuration_ids)
        _require_contiguous_orders("Scene", tuple(scene.order for scene in self.scenes))

        collections = {
            "Prop": tuple(prop.prop_id for prop in self.props),
            "Scene": tuple(scene.scene_id for scene in self.scenes),
            "Line": tuple(line.line_id for line in self.lines),
            "OfflineInput": tuple(
                item.offline_input_id for item in self.offline_inputs
            ),
        }
        for label, identifiers in collections.items():
            _require_unique(f"{label} IDs", identifiers)
        all_ids = (self.backstory.backstory_id,) + tuple(
            identifier
            for identifiers in collections.values()
            for identifier in identifiers
        )
        _require_unique("all Backstory entity IDs", all_ids)

        scenes = {scene.scene_id: scene for scene in self.scenes}
        props = {prop.prop_id: prop for prop in self.props}
        lines = {line.line_id: line for line in self.lines}
        offline_inputs = {
            item.offline_input_id: item for item in self.offline_inputs
        }
        selected_objectives = set(self.objective_ids)
        used_objectives = {
            objective_id
            for scene in self.scenes
            for objective_id in scene.objective_ids
        }
        unused = selected_objectives - used_objectives
        if unused:
            raise ValueError(
                f"selected Objectives without a Scene: {sorted(unused)}"
            )

        for scene in self.scenes:
            if scene.backstory_id != self.backstory.backstory_id:
                raise ValueError(
                    f"Scene {scene.scene_id} references a different Backstory"
                )
            unknown_objectives = set(scene.objective_ids) - selected_objectives
            if unknown_objectives:
                raise ValueError(
                    f"Scene {scene.scene_id} has unselected Objectives: "
                    f"{sorted(unknown_objectives)}"
                )
            _validate_scene_entity_order(scene, lines, offline_inputs)
            _require_known_ids("Prop", scene.scene_id, scene.prop_ids, props)
            _require_known_ids("Line", scene.scene_id, scene.line_ids, lines)
            _require_known_ids(
                "OfflineInput",
                scene.scene_id,
                scene.offline_input_ids,
                offline_inputs,
            )
            for line_id in scene.line_ids:
                if lines[line_id].scene_id != scene.scene_id:
                    raise ValueError(
                        f"Line {line_id} belongs to {lines[line_id].scene_id}, "
                        f"not {scene.scene_id}"
                    )
            for offline_input_id in scene.offline_input_ids:
                item = offline_inputs[offline_input_id]
                if item.scene_id != scene.scene_id:
                    raise ValueError(
                        f"OfflineInput {offline_input_id} belongs to "
                        f"{item.scene_id}, not {scene.scene_id}"
                    )
                _require_known_ids("Prop", offline_input_id, item.prop_ids, props)
                unassigned_props = set(item.prop_ids) - set(scene.prop_ids)
                if unassigned_props:
                    raise ValueError(
                        f"OfflineInput {offline_input_id} uses Props not assigned "
                        f"to Scene {scene.scene_id}: {sorted(unassigned_props)}"
                    )

        for prop in self.props:
            if (
                prop.backstory_id != self.backstory.backstory_id
                or prop.person_id != self.backstory.person_id
                or prop.evaluation_account_id
                != self.backstory.evaluation_account_id
            ):
                raise ValueError(
                    f"Prop {prop.prop_id} is outside the package Backstory, "
                    "person, or evaluation account"
                )
            lifecycle_scenes = {item.scene_id for item in prop.lifecycle}
            unknown_scenes = lifecycle_scenes - set(scenes)
            if unknown_scenes:
                raise ValueError(
                    f"Prop {prop.prop_id} has lifecycle state for unknown Scenes: "
                    f"{sorted(unknown_scenes)}"
                )
            referenced_scenes = {
                scene.scene_id
                for scene in self.scenes
                if prop.prop_id in scene.prop_ids
            }
            if lifecycle_scenes != referenced_scenes:
                raise ValueError(
                    f"Prop {prop.prop_id} lifecycle Scenes must exactly match "
                    "the Scenes that reference it"
                )

        referenced_lines = {
            line_id for scene in self.scenes for line_id in scene.line_ids
        }
        if referenced_lines != set(lines):
            raise ValueError("every Line must be referenced by exactly one Scene")
        referenced_offline_inputs = {
            item_id for scene in self.scenes for item_id in scene.offline_input_ids
        }
        if referenced_offline_inputs != set(offline_inputs):
            raise ValueError(
                "every OfflineInput must be referenced by exactly one Scene"
            )
        return self


def _require_contiguous_orders(label: str, orders: tuple[int, ...]) -> None:
    if tuple(sorted(orders)) != tuple(range(1, len(orders) + 1)):
        raise ValueError(f"{label} orders must be unique and contiguous from 1")


def _require_known_ids(
    label: str,
    owner_id: str,
    identifiers: tuple[str, ...],
    known: dict[str, object],
) -> None:
    unknown = set(identifiers) - set(known)
    if unknown:
        raise ValueError(
            f"{owner_id} references unknown {label} IDs: {sorted(unknown)}"
        )


def _validate_scene_entity_order(
    scene: Scene,
    lines: dict[str, Line],
    offline_inputs: dict[str, OfflineInput],
) -> None:
    known_line_ids = [line_id for line_id in scene.line_ids if line_id in lines]
    if len(known_line_ids) == len(scene.line_ids):
        line_orders = tuple(lines[line_id].order for line_id in scene.line_ids)
        _require_contiguous_orders(f"Scene {scene.scene_id} Line", line_orders)
        if line_orders != tuple(sorted(line_orders)):
            raise ValueError(
                f"Scene {scene.scene_id} line_ids must follow Line order"
            )
    known_offline_ids = [
        item_id for item_id in scene.offline_input_ids if item_id in offline_inputs
    ]
    if len(known_offline_ids) == len(scene.offline_input_ids):
        offline_orders = tuple(
            offline_inputs[item_id].order for item_id in scene.offline_input_ids
        )
        _require_contiguous_orders(
            f"Scene {scene.scene_id} OfflineInput",
            offline_orders,
        )
        if offline_orders != tuple(sorted(offline_orders)):
            raise ValueError(
                f"Scene {scene.scene_id} offline_input_ids must follow input order"
            )


class ExactSpan(StrictModel):
    """An exact Unicode-code-point span in one generated source."""

    source_kind: Literal["line", "prop", "offline_input"]
    source_id: Identifier
    start_codepoint: int = Field(ge=0)
    end_codepoint: int = Field(gt=0)
    text: Text

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.end_codepoint <= self.start_codepoint:
            raise ValueError("end_codepoint must be greater than start_codepoint")
        return self


class PropEvidence(StrictModel):
    kind: Literal["prop"]
    evidence_id: Identifier
    prop_id: Identifier


class PropRelevanceJudgment(StrictModel):
    """Proposed relevance of one available Prop for one Scene."""

    prop_id: Identifier
    relevance: Literal["relevant", "distractor"]


class OfflineInputEvidence(StrictModel):
    kind: Literal["offline_input"]
    evidence_id: Identifier
    offline_input_id: Identifier


class RepositoryTextEvidence(StrictModel):
    kind: Literal["repository_text"]
    evidence_id: Identifier
    repository_path: Text
    source_sha256: Sha256
    start_codepoint: int = Field(ge=0)
    end_codepoint: int = Field(gt=0)
    text: Text

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.end_codepoint <= self.start_codepoint:
            raise ValueError("end_codepoint must be greater than start_codepoint")
        return self


EvidenceReference = Annotated[
    PropEvidence | OfflineInputEvidence | RepositoryTextEvidence,
    Field(discriminator="kind"),
]


class CaptureCandidate(StrictModel):
    kind: Literal["capture_candidate"]
    span: ExactSpan


class NoCandidate(StrictModel):
    kind: Literal["no_candidate"]


CaptureExpectation = Annotated[
    CaptureCandidate | NoCandidate,
    Field(discriminator="kind"),
]

PairField = Literal[
    "backstory_id",
    "fresh_session",
    "prop_ids",
    "line_count",
    "line_text",
    "offline_input_count",
    "offline_input_content",
]


class ScenePairing(StrictModel):
    """Exact fields that a paired Scene must match or differ on."""

    paired_scene_id: Identifier
    match_fields: tuple[PairField, ...] = ()
    difference_fields: tuple[PairField, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        _require_unique("ScenePairing match_fields", self.match_fields)
        _require_unique("ScenePairing difference_fields", self.difference_fields)
        overlap = set(self.match_fields) & set(self.difference_fields)
        if overlap:
            raise ValueError(
                f"ScenePairing fields cannot both match and differ: {sorted(overlap)}"
            )
        return self


class GroundTruthProposal(StrictModel):
    """Generator-authored candidate answer-key data for one Scene and Objective."""

    proposal_id: Identifier
    scene_id: Identifier
    objective_id: Identifier
    expected_outcomes: tuple[Text, ...] = Field(min_length=1)
    prohibited_outcomes: tuple[Text, ...] = Field(min_length=1)
    exact_spans: tuple[ExactSpan, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    prop_relevance: tuple[PropRelevanceJudgment, ...] = ()
    pairing: ScenePairing | None = None
    capture: CaptureExpectation | None = None
    curation: CurationExpectation | None = None
    grounding: GroundingExpectation | None = None

    @model_validator(mode="after")
    def validate_local_uniqueness(self) -> Self:
        _require_unique(
            "GroundTruthProposal evidence IDs",
            tuple(item.evidence_id for item in self.evidence),
        )
        _require_unique(
            "GroundTruthProposal Prop relevance IDs",
            tuple(item.prop_id for item in self.prop_relevance),
        )
        return self

    @model_validator(mode="after")
    def validate_grounding_evidence(self) -> Self:
        """Bind permitted citations to evidence this proposal actually declares."""
        if self.grounding is None:
            return self
        declared = {item.evidence_id for item in self.evidence}
        unknown = sorted(self.grounding.permitted_evidence_ids - declared)
        if unknown:
            raise ValueError(
                f"grounding permits evidence absent from the proposal: {unknown}"
            )
        return self


class ProposedGroundTruth(StrictModel):
    """Proposed Ground truth for one backstory.json file."""

    backstory_sha256: Sha256
    ground_truth_status: Literal["proposed"]
    proposals: tuple[GroundTruthProposal, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_proposal_ids(self) -> Self:
        _require_unique(
            "GroundTruthProposal IDs",
            tuple(proposal.proposal_id for proposal in self.proposals),
        )
        keys = tuple(
            f"{proposal.scene_id}\0{proposal.objective_id}"
            for proposal in self.proposals
        )
        _require_unique("GroundTruthProposal Scene/Objective pairs", keys)
        return self


class HumanGroundTruthReviewer(StrictModel):
    """The human developer who independently reviewed proposed Ground truth."""

    reviewer_id: Text
    reviewer_kind: Literal["human_developer"] = "human_developer"
    review_method: Literal["interactive_local_review"] = (
        "interactive_local_review"
    )


class AdoptedProposalDecision(StrictModel):
    """One human adoption decision bound to one generated proposal."""

    proposal_id: Identifier
    scene_id: Identifier
    objective_id: Identifier
    decision: Literal["adopted"] = "adopted"


class GroundTruthAdoption(StrictModel):
    """Independent human adoption of one exact proposed Ground truth file."""

    backstory_sha256: Sha256
    proposed_ground_truth_sha256: Sha256
    ground_truth_status: Literal["adopted"] = "adopted"
    reviewer: HumanGroundTruthReviewer
    reviewed_at: datetime
    decisions: tuple[AdoptedProposalDecision, ...] = Field(min_length=1)
    adopted_ground_truth_identity: Sha256

    @model_validator(mode="after")
    def validate_decision_ids(self) -> Self:
        _require_unique(
            "adopted Ground truth proposal IDs",
            tuple(decision.proposal_id for decision in self.decisions),
        )
        keys = tuple(
            f"{decision.scene_id}\0{decision.objective_id}"
            for decision in self.decisions
        )
        _require_unique("adopted Ground truth Scene/Objective pairs", keys)
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        return self


class CaptureMix(StrictModel):
    capture_candidate: int = Field(ge=1)
    no_candidate: int = Field(ge=1)


class RetrievalPropMix(StrictModel):
    relevant: int = Field(ge=1)
    distractor: int = Field(ge=1)


class RunConfiguration(StrictModel):
    """Resolved per-run constraints kept outside the Objective catalog."""

    run_configuration_id: Identifier
    objective_id: Identifier
    scene_count: int = Field(ge=1)
    capture_mix: CaptureMix | None = None
    retrieval_prop_mix: RetrievalPropMix | None = None
    no_candidate_material_types: tuple[Text, ...] = ()
    generator_instruction: Text
    dataset_scaling: Text

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        _require_unique(
            "no_candidate_material_types",
            self.no_candidate_material_types,
        )
        configured_mixes = sum(
            mix is not None for mix in (self.capture_mix, self.retrieval_prop_mix)
        )
        if configured_mixes != 1:
            raise ValueError("RunConfiguration requires exactly one mix")
        if self.capture_mix is not None:
            total = (
                self.capture_mix.capture_candidate
                + self.capture_mix.no_candidate
            )
            if total != self.scene_count:
                raise ValueError("capture_mix counts must add up to scene_count")
        return self
