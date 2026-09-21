"""Versioned ordered contract checks for the 4.2.5 Objective."""

import hashlib
import asyncio

import pytest

from evals.synthetic_journals.conversational_surfacing_contract import (
    ConversationalContractError,
    compile_conversational_scenes,
)
from evals.synthetic_journals.conversational_surfacing_replay import (
    replay_conversational_scenes,
)
from evals.synthetic_journals.models import (
    Backstory,
    CaptureCandidate,
    CaptureExpectation,
    ConversationalCaptureExpectation,
    ConversationalSceneSpec,
    ConversationalSourceReference,
    ConversationalSurfacingExpectation,
    ExactSpan,
    GroundTruthProposal,
    Line,
    Prop,
    PropLifecycle,
    ProposedGroundTruth,
    Scene,
    SyntheticBackstory,
)


def _scenario() -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    backstory = Backstory(
        backstory_id="story",
        person_id="person",
        evaluation_account_id="account",
        context="A preference changes through conversation.",
    )
    prop = Prop(
        prop_id="prop-tea",
        backstory_id="story",
        person_id="person",
        evaluation_account_id="account",
        source_text="I prefer mint tea while reading.",
        lifecycle=(
            PropLifecycle(scene_id="capture", state="active"),
            PropLifecycle(scene_id="later", state="active"),
        ),
    )
    capture_line = "I now prefer jasmine tea while reading."
    capture = Scene(
        scene_id="capture",
        backstory_id="story",
        objective_ids=("proactive_memory_surfacing",),
        order=1,
        fresh_session=True,
        prop_ids=("prop-tea",),
        line_ids=("line-capture",),
    )
    later = Scene(
        scene_id="later",
        backstory_id="story",
        objective_ids=("proactive_memory_surfacing",),
        order=2,
        fresh_session=True,
        prop_ids=("prop-tea",),
        line_ids=("line-later",),
    )
    scenario = SyntheticBackstory(
        objective_ids=("proactive_memory_surfacing",),
        scenario_contract="conversational_v1",
        backstory=backstory,
        props=(prop,),
        scenes=(capture, later),
        lines=(
            Line(
                line_id="line-capture",
                scene_id="capture",
                order=1,
                text=capture_line,
            ),
            Line(
                line_id="line-later",
                scene_id="later",
                order=1,
                text="What should I make before reading tonight?",
            ),
        ),
        conversational_scenes=(
            ConversationalSceneSpec(scene_id="capture", kind="capture"),
            ConversationalSceneSpec(
                scene_id="later",
                kind="surfacing",
                prerequisite_scene_ids=("capture",),
            ),
        ),
    )
    capture_expectation = ConversationalCaptureExpectation(
        capture=CaptureExpectation(
            nomination=CaptureCandidate(
                kind="capture_candidate",
                span=ExactSpan(
                    source_kind="line",
                    source_id="line-capture",
                    start_codepoint=5,
                    end_codepoint=len(capture_line) - 1,
                    text=capture_line[5:-1],
                ),
            ),
            provenance_decision="allow_capture",
        ),
        curation_status="applied",
        curation_source_references=(
            ConversationalSourceReference(kind="source_prop", reference="prop-tea"),
            ConversationalSourceReference(
                kind="captured_memory", reference="capture:new-memory"
            ),
        ),
    )
    surfacing_expectation = ConversationalSurfacingExpectation(
        decision="surface_now",
        required_source_references=(
            ConversationalSourceReference(
                kind="curated_memory", reference="capture:retrieval-view"
            ),
        ),
        allowed_source_references=(
            ConversationalSourceReference(
                kind="curated_memory", reference="capture:retrieval-view"
            ),
        ),
        semantic_criteria=("Use the updated preference without exposing internal IDs.",),
        release="released",
    )
    ground_truth = ProposedGroundTruth(
        backstory_sha256=hashlib.sha256(backstory.model_dump_json().encode()).hexdigest(),
        ground_truth_status="proposed",
        scenario_contract="conversational_v1",
        proposals=(
            GroundTruthProposal(
                proposal_id="proposal-capture",
                scene_id="capture",
                objective_id="proactive_memory_surfacing",
                expected_outcomes=("Capture the exact preference update.",),
                prohibited_outcomes=("Write an unreviewed memory.",),
                conversational=capture_expectation,
            ),
            GroundTruthProposal(
                proposal_id="proposal-later",
                scene_id="later",
                objective_id="proactive_memory_surfacing",
                expected_outcomes=("Use the updated preference when useful.",),
                prohibited_outcomes=("Bypass Provenance release review.",),
                conversational=surfacing_expectation,
            ),
        ),
    )
    return scenario, ground_truth


def test_conversational_v1_compiles_ordered_lines_and_symbolic_outcomes() -> None:
    backstory, ground_truth = _scenario()

    compiled = compile_conversational_scenes(backstory, ground_truth)

    assert [item.scene.scene_id for item in compiled] == ["capture", "later"]
    assert compiled[1].workflow.prerequisite_scene_ids == ("capture",)
    assert compiled[0].expectation.kind == "capture"
    assert compiled[1].expectation.kind == "surfacing"


def test_component_contract_remains_the_default_for_existing_scenarios() -> None:
    from tests.surfacing_fixtures import make_surfacing_scenario
    from evals.synthetic_journals.surfacing_contract import compile_surfacing_scenes

    backstory, ground_truth = make_surfacing_scenario()

    assert backstory.scenario_contract == "component_v1"
    assert ground_truth.scenario_contract == "component_v1"
    assert len(compile_surfacing_scenes(backstory, ground_truth)) == 6


def test_conversational_contract_rejects_future_prerequisite() -> None:
    backstory, ground_truth = _scenario()
    spec = backstory.conversational_scenes[1].model_copy(
        update={"prerequisite_scene_ids": ("missing",)}
    )
    broken = backstory.model_copy(
        update={"conversational_scenes": (backstory.conversational_scenes[0], spec)}
    )

    with pytest.raises(ConversationalContractError, match="prerequisites"):
        compile_conversational_scenes(broken, ground_truth)


def test_ordered_replay_refuses_component_v1_inputs() -> None:
    from tests.surfacing_fixtures import make_surfacing_scenario

    backstory, ground_truth = make_surfacing_scenario()

    with pytest.raises(ConversationalContractError, match="conversational_v1"):
        asyncio.run(replay_conversational_scenes(backstory, ground_truth))
