"""Validate a synthetic Backstory and proposed Ground truth deterministically."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evals.sculptor.harness import ExpectedCurationProposal, REQUIRED_BEHAVIORS
from evals.synthetic_journals.models import (
    CaptureCandidate,
    ExactSpan,
    GroundTruthProposal,
    OfflineInputEvidence,
    PropEvidence,
    ProposedGroundTruth,
    RepositoryTextEvidence,
    RunConfiguration,
    Scene,
    SyntheticBackstory,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_CONFIGURATION_DIRECTORY = (
    REPOSITORY_ROOT / "synthetic-journal-evaluation" / "run-configurations"
)
BOUNDED_CURATION_OBJECTIVE_ID = "bounded_memory_curation"
GROUNDED_BOOK_REFLECTION_OBJECTIVE_ID = "grounded_book_reflection"
SPOILER_BOUNDARY_OBJECTIVE_ID = "spoiler_boundary_clarification"


class PackageValidationError(ValueError):
    """One or more deterministic package checks failed."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        super().__init__("; ".join(failures))


def validate_package_files(
    backstory_path: Path,
    ground_truth_path: Path,
    *,
    run_configuration_directory: Path = DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    repository_root: Path = REPOSITORY_ROOT,
) -> tuple[SyntheticBackstory, ProposedGroundTruth]:
    """Load two JSON files and validate their complete package graph."""

    backstory_bytes = backstory_path.read_bytes()
    ground_truth_bytes = ground_truth_path.read_bytes()
    try:
        backstory = SyntheticBackstory.model_validate_json(backstory_bytes)
        ground_truth = ProposedGroundTruth.model_validate_json(ground_truth_bytes)
    except ValidationError as error:
        raise PackageValidationError([_format_pydantic_error(error)]) from error

    configurations = load_run_configurations(run_configuration_directory)
    validate_package(
        backstory,
        ground_truth,
        backstory_bytes=backstory_bytes,
        run_configurations=configurations,
        repository_root=repository_root,
    )
    return backstory, ground_truth


def load_run_configurations(directory: Path) -> dict[str, RunConfiguration]:
    """Load strict JSON run configurations from a repository directory."""

    configurations: dict[str, RunConfiguration] = {}
    if not directory.is_dir():
        return configurations
    for path in sorted(directory.glob("*.json")):
        try:
            configuration = RunConfiguration.model_validate_json(path.read_bytes())
        except ValidationError as error:
            raise PackageValidationError(
                [f"invalid run configuration {path}: {_format_pydantic_error(error)}"]
            ) from error
        if configuration.run_configuration_id in configurations:
            raise PackageValidationError(
                [
                    "duplicate run configuration ID: "
                    f"{configuration.run_configuration_id}"
                ]
            )
        configurations[configuration.run_configuration_id] = configuration
    return configurations


def validate_package(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    backstory_bytes: bytes,
    run_configurations: dict[str, RunConfiguration],
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    """Check hash, graph, spans, evidence, pairings, and run configuration."""

    failures: list[str] = []
    actual_hash = hashlib.sha256(backstory_bytes).hexdigest()
    if ground_truth.backstory_sha256 != actual_hash:
        failures.append(
            "backstory_sha256 does not match the exact backstory.json bytes"
        )

    scenes = {scene.scene_id: scene for scene in backstory.scenes}
    props = {prop.prop_id: prop for prop in backstory.props}
    lines = {line.line_id: line for line in backstory.lines}
    offline_inputs = {
        item.offline_input_id: item for item in backstory.offline_inputs
    }
    expected_proposals = {
        (scene.scene_id, objective_id)
        for scene in backstory.scenes
        for objective_id in scene.objective_ids
    }
    actual_proposals = {
        (proposal.scene_id, proposal.objective_id)
        for proposal in ground_truth.proposals
    }
    missing_proposals = expected_proposals - actual_proposals
    extra_proposals = actual_proposals - expected_proposals
    if missing_proposals:
        failures.append(
            f"missing Ground truth proposals: {_format_pairs(missing_proposals)}"
        )
    if extra_proposals:
        failures.append(
            f"unexpected Ground truth proposals: {_format_pairs(extra_proposals)}"
        )

    evidence_ids: set[str] = set()
    for proposal in ground_truth.proposals:
        scene = scenes.get(proposal.scene_id)
        if scene is None:
            continue
        for span in proposal.exact_spans:
            failures.extend(
                _validate_span(span, scene, props, lines, offline_inputs)
            )
        if isinstance(proposal.capture, CaptureCandidate):
            failures.extend(
                _validate_span(
                    proposal.capture.span,
                    scene,
                    props,
                    lines,
                    offline_inputs,
                )
            )
        for evidence in proposal.evidence:
            if evidence.evidence_id in evidence_ids:
                failures.append(
                    f"duplicate evidence ID across Ground truth: {evidence.evidence_id}"
                )
            evidence_ids.add(evidence.evidence_id)
            failures.extend(
                _validate_evidence(
                    evidence,
                    scene,
                    props,
                    offline_inputs,
                    repository_root,
                )
            )
        if proposal.pairing is not None:
            failures.extend(
                _validate_pairing(
                    proposal,
                    scene,
                    scenes,
                    lines,
                    offline_inputs,
                )
            )

    failures.extend(
        _validate_book_objectives(ground_truth, scenes, props)
    )
    failures.extend(
        _validate_bounded_curation(backstory, ground_truth, props)
    )
    failures.extend(
        _validate_run_configurations(backstory, ground_truth, run_configurations)
    )
    if failures:
        raise PackageValidationError(failures)


def _validate_book_objectives(
    ground_truth: ProposedGroundTruth,
    scenes: dict[str, Scene],
    props: dict[str, Any],
) -> list[str]:
    """Validate typed Ground truth required by book replay Objectives."""

    failures: list[str] = []
    for proposal in ground_truth.proposals:
        scene = scenes.get(proposal.scene_id)
        if scene is None:
            continue
        grounded = proposal.grounded_book_reflection
        spoiler = proposal.spoiler_boundary

        if proposal.objective_id == GROUNDED_BOOK_REFLECTION_OBJECTIVE_ID:
            if grounded is None:
                failures.append(
                    f"grounded reflection proposal {proposal.proposal_id} lacks "
                    "typed grounded_book_reflection Ground truth"
                )
            if spoiler is not None:
                failures.append(
                    f"grounded reflection proposal {proposal.proposal_id} has "
                    "spoiler-boundary Ground truth"
                )
        elif grounded is not None:
            failures.append(
                f"proposal {proposal.proposal_id} has grounded reflection Ground "
                f"truth for Objective {proposal.objective_id}"
            )

        if proposal.objective_id == SPOILER_BOUNDARY_OBJECTIVE_ID:
            if spoiler is None:
                failures.append(
                    f"spoiler proposal {proposal.proposal_id} lacks typed "
                    "spoiler_boundary Ground truth"
                )
            if grounded is not None:
                failures.append(
                    f"spoiler proposal {proposal.proposal_id} has grounded "
                    "reflection Ground truth"
                )
        elif spoiler is not None:
            failures.append(
                f"proposal {proposal.proposal_id} has spoiler-boundary Ground "
                f"truth for Objective {proposal.objective_id}"
            )

        evidence = {item.evidence_id: item for item in proposal.evidence}
        if grounded is not None:
            referenced_ids = set(grounded.permitted_evidence_ids)
            failures.extend(
                _require_repository_evidence_ids(
                    proposal.proposal_id,
                    "grounded reflection",
                    referenced_ids,
                    evidence,
                )
            )

        if spoiler is None:
            continue
        unknown_props = set(spoiler.authorised_prop_ids) - set(scene.prop_ids)
        if unknown_props:
            failures.append(
                f"spoiler proposal {proposal.proposal_id} authorises Props outside "
                f"Scene {scene.scene_id}: {sorted(unknown_props)}"
            )
        for prop_id in spoiler.authorised_prop_ids:
            prop = props.get(prop_id)
            if prop is None or prop_id not in scene.prop_ids:
                continue
            lifecycle = next(
                item for item in prop.lifecycle if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                failures.append(
                    f"spoiler Prop {prop_id} must be active for Scene {scene.scene_id}"
                )

        prop_span_ids = {
            span.source_id
            for span in proposal.exact_spans
            if span.source_kind == "prop"
        }
        missing_prop_spans = set(spoiler.authorised_prop_ids) - prop_span_ids
        if missing_prop_spans:
            failures.append(
                f"spoiler proposal {proposal.proposal_id} lacks exact spans for "
                f"authorised Props: {sorted(missing_prop_spans)}"
            )
        if not any(
            span.source_kind == "line" for span in proposal.exact_spans
        ):
            failures.append(
                f"spoiler proposal {proposal.proposal_id} requires an exact Line span"
            )

        referenced_ids = set(spoiler.supporting_evidence_ids) | set(
            spoiler.forbidden_later_evidence_ids
        )
        failures.extend(
            _require_repository_evidence_ids(
                proposal.proposal_id,
                "spoiler boundary",
                referenced_ids,
                evidence,
            )
        )
    return failures


def _require_repository_evidence_ids(
    proposal_id: str,
    label: str,
    evidence_ids: set[str],
    evidence: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    missing = evidence_ids - set(evidence)
    if missing:
        failures.append(
            f"{label} proposal {proposal_id} references missing evidence IDs: "
            f"{sorted(missing)}"
        )
    wrong_kind = sorted(
        evidence_id
        for evidence_id in evidence_ids & set(evidence)
        if not isinstance(evidence[evidence_id], RepositoryTextEvidence)
    )
    if wrong_kind:
        failures.append(
            f"{label} proposal {proposal_id} requires repository-text evidence: "
            f"{wrong_kind}"
        )
    return failures


def _validate_bounded_curation(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    props: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    curation_scenes = [
        scene
        for scene in backstory.scenes
        if BOUNDED_CURATION_OBJECTIVE_ID in scene.objective_ids
    ]
    proposals = {
        proposal.scene_id: proposal
        for proposal in ground_truth.proposals
        if proposal.objective_id == BOUNDED_CURATION_OBJECTIVE_ID
    }

    for proposal in ground_truth.proposals:
        if (
            proposal.objective_id != BOUNDED_CURATION_OBJECTIVE_ID
            and proposal.curation is not None
        ):
            failures.append(
                f"proposal {proposal.proposal_id} has curation Ground truth for "
                f"Objective {proposal.objective_id}"
            )

    if not curation_scenes:
        return failures

    observed_behaviors = []
    for scene in curation_scenes:
        proposal = proposals.get(scene.scene_id)
        if proposal is None:  # Covered by the general proposal topology check.
            continue
        if proposal.curation is None:
            failures.append(
                f"bounded curation proposal {proposal.proposal_id} lacks typed "
                "curation Ground truth"
            )
            continue
        observed_behaviors.append(proposal.curation.primary_behavior)

        if scene.line_ids or scene.offline_input_ids:
            failures.append(
                f"bounded curation Scene {scene.scene_id} accepts Props only"
            )
        if not 2 <= len(scene.prop_ids) <= 12:
            failures.append(
                f"bounded curation Scene {scene.scene_id} requires 2-12 Props"
            )
        for prop_id in scene.prop_ids:
            prop = props[prop_id]
            lifecycle = next(
                item for item in prop.lifecycle if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                failures.append(
                    f"bounded curation Prop {prop_id} must be active for "
                    f"Scene {scene.scene_id}"
                )

        evidence_prop_ids = [
            evidence.prop_id
            for evidence in proposal.evidence
            if isinstance(evidence, PropEvidence)
        ]
        if len(evidence_prop_ids) != len(proposal.evidence):
            failures.append(
                f"bounded curation proposal {proposal.proposal_id} permits only "
                "Prop evidence"
            )
        if (
            len(evidence_prop_ids) != len(scene.prop_ids)
            or set(evidence_prop_ids) != set(scene.prop_ids)
        ):
            failures.append(
                f"bounded curation proposal {proposal.proposal_id} must cite "
                "every Scene Prop exactly once"
            )
        if not proposal.exact_spans or any(
            span.source_kind != "prop" for span in proposal.exact_spans
        ):
            failures.append(
                f"bounded curation proposal {proposal.proposal_id} requires "
                "exact Prop spans"
            )
        if proposal.capture is not None or proposal.prop_relevance:
            failures.append(
                f"bounded curation proposal {proposal.proposal_id} cannot contain "
                "capture or retrieval labels"
            )

        expected = proposal.curation.expected
        if isinstance(expected, ExpectedCurationProposal):
            source_ids = expected.action.source_memory_ids
            if len(source_ids) != len(set(source_ids)):
                failures.append(
                    f"bounded curation proposal {proposal.proposal_id} has "
                    "duplicate expected source IDs"
                )
            unknown_sources = set(source_ids) - set(scene.prop_ids)
            if unknown_sources:
                failures.append(
                    f"bounded curation proposal {proposal.proposal_id} expects "
                    f"Props outside its Scene: {sorted(unknown_sources)}"
                )
            span_prop_ids = {
                span.source_id
                for span in proposal.exact_spans
                if span.source_kind == "prop"
            }
            unsupported_sources = set(source_ids) - span_prop_ids
            if unsupported_sources:
                failures.append(
                    f"bounded curation proposal {proposal.proposal_id} lacks "
                    f"exact spans for expected sources: {sorted(unsupported_sources)}"
                )

    if (
        len(observed_behaviors) != len(REQUIRED_BEHAVIORS)
        or set(observed_behaviors) != REQUIRED_BEHAVIORS
    ):
        failures.append(
            "bounded curation package must contain exactly one Scene for each "
            "accepted Sculptor behavior"
        )
    return failures


def _validate_span(
    span: ExactSpan,
    scene: Scene,
    props: dict[str, Any],
    lines: dict[str, Any],
    offline_inputs: dict[str, Any],
) -> list[str]:
    sources: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {
        "line": (lines, scene.line_ids),
        "prop": (props, scene.prop_ids),
        "offline_input": (offline_inputs, scene.offline_input_ids),
    }
    source_map, allowed_ids = sources[span.source_kind]
    source = source_map.get(span.source_id)
    if source is None:
        return [
            f"proposal for {scene.scene_id} references unknown "
            f"{span.source_kind} span source {span.source_id}"
        ]
    if span.source_id not in allowed_ids:
        return [
            f"span source {span.source_id} is not assigned to Scene {scene.scene_id}"
        ]
    source_text = source.source_text if span.source_kind == "prop" else source.text
    if source_text is None:
        return [f"span source {span.source_id} has no text"]
    actual_text = source_text[span.start_codepoint : span.end_codepoint]
    if actual_text != span.text:
        return [
            f"span text mismatch for {span.source_id}: expected exact code-point slice"
        ]
    return []


def _validate_evidence(
    evidence: Any,
    scene: Scene,
    props: dict[str, Any],
    offline_inputs: dict[str, Any],
    repository_root: Path,
) -> list[str]:
    if isinstance(evidence, PropEvidence):
        if evidence.prop_id not in props:
            return [f"evidence {evidence.evidence_id} references unknown Prop"]
        if evidence.prop_id not in scene.prop_ids:
            return [
                f"evidence {evidence.evidence_id} Prop is not assigned to "
                f"Scene {scene.scene_id}"
            ]
        return []
    if isinstance(evidence, OfflineInputEvidence):
        if evidence.offline_input_id not in offline_inputs:
            return [
                f"evidence {evidence.evidence_id} references unknown OfflineInput"
            ]
        if evidence.offline_input_id not in scene.offline_input_ids:
            return [
                f"evidence {evidence.evidence_id} OfflineInput is not assigned to "
                f"Scene {scene.scene_id}"
            ]
        return []
    if isinstance(evidence, RepositoryTextEvidence):
        return _validate_repository_evidence(evidence, repository_root)
    return [f"unsupported evidence reference {evidence.evidence_id}"]


def _validate_repository_evidence(
    evidence: RepositoryTextEvidence,
    repository_root: Path,
) -> list[str]:
    relative_path = Path(evidence.repository_path)
    if relative_path.is_absolute():
        return [f"evidence {evidence.evidence_id} path must be repository-relative"]
    root = repository_root.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return [f"evidence {evidence.evidence_id} path escapes the repository"]
    if not path.is_file():
        return [f"evidence {evidence.evidence_id} repository file does not exist"]
    source_bytes = path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != evidence.source_sha256:
        return [f"evidence {evidence.evidence_id} source_sha256 does not match"]
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return [f"evidence {evidence.evidence_id} repository file is not UTF-8"]
    actual_text = source_text[
        evidence.start_codepoint : evidence.end_codepoint
    ]
    if actual_text != evidence.text:
        return [f"evidence {evidence.evidence_id} exact text span does not match"]
    return []


def _validate_pairing(
    proposal: GroundTruthProposal,
    scene: Scene,
    scenes: dict[str, Scene],
    lines: dict[str, Any],
    offline_inputs: dict[str, Any],
) -> list[str]:
    assert proposal.pairing is not None
    paired_scene = scenes.get(proposal.pairing.paired_scene_id)
    if paired_scene is None:
        return [
            f"proposal {proposal.proposal_id} pairs with unknown Scene "
            f"{proposal.pairing.paired_scene_id}"
        ]
    if paired_scene.scene_id == scene.scene_id:
        return [f"proposal {proposal.proposal_id} cannot pair a Scene with itself"]
    if proposal.objective_id not in paired_scene.objective_ids:
        return [
            f"paired Scene {paired_scene.scene_id} does not include Objective "
            f"{proposal.objective_id}"
        ]
    failures: list[str] = []
    for field in proposal.pairing.match_fields:
        if _pair_field(scene, field, lines, offline_inputs) != _pair_field(
            paired_scene, field, lines, offline_inputs
        ):
            failures.append(
                f"paired Scenes {scene.scene_id} and {paired_scene.scene_id} "
                f"must match on {field}"
            )
    for field in proposal.pairing.difference_fields:
        if _pair_field(scene, field, lines, offline_inputs) == _pair_field(
            paired_scene, field, lines, offline_inputs
        ):
            failures.append(
                f"paired Scenes {scene.scene_id} and {paired_scene.scene_id} "
                f"must differ on {field}"
            )
    return failures


def _pair_field(
    scene: Scene,
    field: str,
    lines: dict[str, Any],
    offline_inputs: dict[str, Any],
) -> Any:
    values = {
        "backstory_id": scene.backstory_id,
        "fresh_session": scene.fresh_session,
        "prop_ids": scene.prop_ids,
        "line_count": len(scene.line_ids),
        "line_text": tuple(lines[line_id].text for line_id in scene.line_ids),
        "offline_input_count": len(scene.offline_input_ids),
        "offline_input_content": tuple(
            (
                offline_inputs[item_id].kind,
                offline_inputs[item_id].text,
                offline_inputs[item_id].prop_ids,
            )
            for item_id in scene.offline_input_ids
        ),
    }
    return values[field]


def _validate_run_configurations(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    configurations: dict[str, RunConfiguration],
) -> list[str]:
    failures: list[str] = []
    for configuration_id in backstory.run_configuration_ids:
        configuration = configurations.get(configuration_id)
        if configuration is None:
            failures.append(f"unknown run configuration: {configuration_id}")
            continue
        if configuration.objective_id not in backstory.objective_ids:
            failures.append(
                f"run configuration {configuration_id} targets unselected Objective "
                f"{configuration.objective_id}"
            )
            continue
        scenes = [
            scene
            for scene in backstory.scenes
            if configuration.objective_id in scene.objective_ids
        ]
        if len(scenes) != configuration.scene_count:
            failures.append(
                f"run configuration {configuration_id} requires "
                f"{configuration.scene_count} Scenes, found {len(scenes)}"
            )
        if configuration.capture_mix is not None:
            proposals = [
                proposal
                for proposal in ground_truth.proposals
                if proposal.objective_id == configuration.objective_id
            ]
            capture_candidates = [
                proposal
                for proposal in proposals
                if isinstance(proposal.capture, CaptureCandidate)
            ]
            no_candidates = [
                proposal
                for proposal in proposals
                if proposal.capture is not None
                and proposal.capture.kind == "no_candidate"
            ]
            missing_capture = [
                proposal.proposal_id
                for proposal in proposals
                if proposal.capture is None
            ]
            proposals_with_generic_spans = [
                proposal.proposal_id
                for proposal in proposals
                if proposal.exact_spans
            ]
            if missing_capture:
                failures.append(
                    f"run configuration {configuration_id} requires a capture "
                    f"proposal for every Scene; missing: {sorted(missing_capture)}"
                )
            if proposals_with_generic_spans:
                failures.append(
                    f"run configuration {configuration_id} records capture spans "
                    "only in capture_candidate; generic exact_spans found in: "
                    f"{sorted(proposals_with_generic_spans)}"
                )
            if (
                len(capture_candidates)
                != configuration.capture_mix.capture_candidate
            ):
                failures.append(
                    f"run configuration {configuration_id} requires "
                    f"{configuration.capture_mix.capture_candidate} "
                    f"capture_candidate proposal(s), found {len(capture_candidates)}"
                )
            if len(no_candidates) != configuration.capture_mix.no_candidate:
                failures.append(
                    f"run configuration {configuration_id} requires "
                    f"{configuration.capture_mix.no_candidate} no_candidate "
                    f"proposal(s), found {len(no_candidates)}"
                )
            for proposal in capture_candidates:
                assert isinstance(proposal.capture, CaptureCandidate)
                if proposal.capture.span.source_kind != "line":
                    failures.append(
                        f"capture candidate {proposal.proposal_id} must use an "
                        "exact Line span"
                    )
        if configuration.retrieval_prop_mix is not None:
            failures.extend(
                _validate_retrieval_prop_mix(
                    configuration,
                    scenes,
                    backstory,
                    ground_truth,
                )
            )
    return failures


def _validate_retrieval_prop_mix(
    configuration: RunConfiguration,
    scenes: list[Scene],
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
) -> list[str]:
    mix = configuration.retrieval_prop_mix
    assert mix is not None
    if len(scenes) != configuration.scene_count:
        return []

    failures: list[str] = []
    expected_prop_count = mix.relevant + mix.distractor
    expected_prop_ids = set(scenes[0].prop_ids)
    if len(expected_prop_ids) != expected_prop_count:
        failures.append(
            f"run configuration {configuration.run_configuration_id} requires "
            f"{expected_prop_count} Props per retrieval Scene, found "
            f"{len(expected_prop_ids)} in {scenes[0].scene_id}"
        )
    for scene in scenes[1:]:
        if set(scene.prop_ids) != expected_prop_ids:
            failures.append(
                f"run configuration {configuration.run_configuration_id} requires "
                "all retrieval Scenes to share the same Prop bank"
            )

    props = {prop.prop_id: prop for prop in backstory.props}
    for scene in scenes:
        for prop_id in scene.prop_ids:
            prop = props[prop_id]
            lifecycle = next(
                item for item in prop.lifecycle if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                failures.append(
                    f"run configuration {configuration.run_configuration_id} "
                    f"requires Prop {prop_id} to be active for {scene.scene_id}"
                )

    scene_ids = {scene.scene_id for scene in scenes}
    proposals = {
        proposal.scene_id: proposal
        for proposal in ground_truth.proposals
        if proposal.objective_id == configuration.objective_id
        and proposal.scene_id in scene_ids
    }
    observed_mixes: list[tuple[int, int]] = []
    for scene in scenes:
        proposal = proposals.get(scene.scene_id)
        if proposal is None:
            continue
        judgments = {item.prop_id: item.relevance for item in proposal.prop_relevance}
        if set(judgments) != set(scene.prop_ids):
            failures.append(
                f"run configuration {configuration.run_configuration_id} requires "
                f"one Prop relevance judgment for every Prop in {scene.scene_id}"
            )
            continue
        relevant_ids = {
            prop_id
            for prop_id, relevance in judgments.items()
            if relevance == "relevant"
        }
        distractor_ids = set(judgments) - relevant_ids
        observed_mixes.append((len(relevant_ids), len(distractor_ids)))
        evidence_prop_ids = [
            evidence.prop_id
            for evidence in proposal.evidence
            if isinstance(evidence, PropEvidence)
        ]
        if len(evidence_prop_ids) != len(set(evidence_prop_ids)):
            failures.append(
                f"proposal {proposal.proposal_id} repeats Prop evidence"
            )
        if set(evidence_prop_ids) != relevant_ids:
            failures.append(
                f"proposal {proposal.proposal_id} Prop evidence must exactly match "
                "its relevant Prop judgments"
            )

    required_mixes = sorted(
        [
            (mix.relevant, mix.distractor),
            (0, expected_prop_count),
        ]
    )
    if sorted(observed_mixes) != required_mixes:
        failures.append(
            f"run configuration {configuration.run_configuration_id} requires "
            f"retrieval Prop mixes {required_mixes}, found {sorted(observed_mixes)}"
        )
    return failures


def _format_pydantic_error(error: ValidationError) -> str:
    messages = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"]) or "document"
        messages.append(f"{location}: {item['msg']}")
    return " | ".join(messages)


def _format_pairs(pairs: set[tuple[str, str]]) -> str:
    return ", ".join(
        f"{scene_id}/{objective_id}"
        for scene_id, objective_id in sorted(pairs)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate backstory.json and ground-truth.json."
    )
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument(
        "--run-configuration-directory",
        type=Path,
        default=DEFAULT_RUN_CONFIGURATION_DIRECTORY,
    )
    args = parser.parse_args(argv)
    try:
        backstory, ground_truth = validate_package_files(
            args.backstory,
            args.ground_truth,
            run_configuration_directory=args.run_configuration_directory,
        )
    except (OSError, PackageValidationError) as error:
        print(f"PACKAGE_VALIDATION_FAILED={error}", file=sys.stderr)
        return 1
    print(
        "PACKAGE_VALIDATION_OK="
        f"{len(backstory.scenes)} scenes,{len(ground_truth.proposals)} proposals"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
