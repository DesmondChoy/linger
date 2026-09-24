"""Resolve trusted connection inputs separately from adoptable outcome labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .book_evidence import BookEvidenceResolver, ResolvedCorpusSpan
from .models import (
    GroundTruthProposal,
    Line,
    Prop,
    PropEvidence,
    ProposedGroundTruth,
    PublicSourceEvidence,
    RepositoryTextEvidence,
    Scene,
    SceneSourceSetup,
    SyntheticBackstory,
)

CONNECTION_OBJECTIVE_ID = "cross_source_tentative_connection"
WEAK_EVIDENCE_OBJECTIVE_ID = "weak_evidence_safe_decline"
CONNECTION_OBJECTIVE_IDS = frozenset({CONNECTION_OBJECTIVE_ID, WEAK_EVIDENCE_OBJECTIVE_ID})
CONNECTION_CURATION_OBJECTIVE_IDS = frozenset({CONNECTION_OBJECTIVE_ID, "bounded_memory_curation"})
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ConnectionContractError(ValueError):
    """A connection scenario cannot be executed under its declared authority."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        super().__init__("; ".join(failures))


@dataclass(frozen=True)
class ValidatedConnectionScene:
    scene: Scene
    line: Line
    props: tuple[Prop, ...]
    source_setup: SceneSourceSetup | None
    evidence_by_id: dict[str, ResolvedCorpusSpan]
    proposals: tuple[GroundTruthProposal, ...]


@dataclass(frozen=True)
class ConnectionReplayPlan:
    backstory: SyntheticBackstory
    ground_truth: ProposedGroundTruth
    objective_ids: frozenset[str]
    scenes: tuple[ValidatedConnectionScene, ...]


def compile_connection_replay_plan(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> ConnectionReplayPlan:
    """Validate source identity and compile one-account, isolated Scene inputs."""
    from .validate_scenario import _pair_field, _validate_evidence, _validate_pairing, _validate_span

    selected = frozenset(backstory.objective_ids)
    with_curation = selected == CONNECTION_CURATION_OBJECTIVE_IDS
    if not selected or not (selected <= CONNECTION_OBJECTIVE_IDS or with_curation):
        raise ConnectionContractError([
            "connection compilation accepts connection, weak evidence, their pair, "
            "or exactly connection with bounded curation"
        ])
    if with_curation and any(len(scene.objective_ids) != 1 for scene in backstory.scenes):
        raise ConnectionContractError(["combined connection and curation Scenes must select exactly one Objective"])
    connection_objectives = selected & CONNECTION_OBJECTIVE_IDS
    failures: list[str] = []
    if backstory.run_configuration_ids or backstory.offline_inputs:
        failures.append("connection replay accepts no run configuration or offline inputs")
    if ground_truth.book_scene_facts:
        failures.append("connection book setup belongs to Backstory source_setups, not Ground truth")
    expected = {(scene.scene_id, objective) for scene in backstory.scenes for objective in scene.objective_ids}
    actual = {(proposal.scene_id, proposal.objective_id) for proposal in ground_truth.proposals}
    if expected != actual:
        raise ConnectionContractError(["connection proposal coverage must exactly match Scene Objectives"])
    scenes = {scene.scene_id: scene for scene in backstory.scenes}
    setups = {setup.scene_id: setup for setup in backstory.source_setups}
    props = {prop.prop_id: prop for prop in backstory.props}
    lines = {line.line_id: line for line in backstory.lines}
    resolver = BookEvidenceResolver(repository_root)
    compiled: list[ValidatedConnectionScene] = []
    decisions: dict[str, set[str]] = {objective: set() for objective in connection_objectives}
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        if not connection_objectives.intersection(scene.objective_ids):
            continue
        if not scene.fresh_session or len(scene.line_ids) != 1 or scene.offline_input_ids:
            failures.append(f"connection Scene {scene.scene_id} requires a fresh session, one Line, and no offline input")
            continue
        setup = setups.get(scene.scene_id)
        scene_props = tuple(props[prop_id] for prop_id in scene.prop_ids)
        for prop in scene_props:
            state = next(item.state for item in prop.lifecycle if item.scene_id == scene.scene_id)
            if state != "active":
                failures.append(f"connection Scene {scene.scene_id} requires active Prop {prop.prop_id}")
        scene_proposals = tuple(
            proposal for proposal in ground_truth.proposals if proposal.scene_id == scene.scene_id
        )
        evidence_by_id: dict[str, ResolvedCorpusSpan] = {}
        for scope in setup.book_scopes if setup else ():
            try:
                if scope.safe_ceiling_chapter > resolver.max_chapter(scope.work_id, scope.book_version_id):
                    failures.append(f"Scene {scene.scene_id} book ceiling exceeds corpus")
            except (OSError, ValueError) as error:
                failures.append(f"Scene {scene.scene_id} corpus integrity: {error}")
        for proposal in scene_proposals:
            expectation = proposal.connection
            if expectation is None:
                failures.append(f"proposal {proposal.proposal_id} requires typed connection Ground truth")
                continue
            decisions[proposal.objective_id].add(expectation.decision)
            if proposal.pairing is None:
                failures.append(f"proposal {proposal.proposal_id} requires a contrasting Scene pairing")
            else:
                failures.extend(_validate_pairing(proposal, scene, scenes, lines, {}, setups))
                paired = scenes.get(proposal.pairing.paired_scene_id)
                if paired is not None:
                    material_fields = {"backstory_id", "fresh_session", "prop_ids", "line_count", "line_text", "source_setup"}
                    actual_differences = {
                        field for field in material_fields
                        if _pair_field(scene, field, lines, {}, setups) != _pair_field(paired, field, lines, {}, setups)
                    }
                    undeclared = actual_differences - set(proposal.pairing.difference_fields)
                    if undeclared:
                        failures.append(f"proposal {proposal.proposal_id} has undeclared paired differences: {sorted(undeclared)}")
            if {item.prop_id for item in proposal.prop_relevance} != set(scene.prop_ids):
                failures.append(f"proposal {proposal.proposal_id} requires one Prop relevance judgment for every available Prop")
            for span in proposal.exact_spans:
                failures.extend(_validate_span(span, scene, props, lines, {}))
            for evidence in proposal.evidence:
                failures.extend(_validate_evidence(evidence, scene, props, {}, repository_root, setup))
                if isinstance(evidence, RepositoryTextEvidence):
                    try:
                        evidence_by_id[evidence.evidence_id] = _resolve_book_evidence(
                            evidence, setup, resolver
                        )
                    except (OSError, ValueError) as error:
                        failures.append(f"evidence {evidence.evidence_id}: {error}")
                elif not isinstance(evidence, (PropEvidence, PublicSourceEvidence)):
                    failures.append(f"connection proposal {proposal.proposal_id} contains unsupported evidence")
            available_books = {scope.work_id for scope in setup.book_scopes} if setup else set()
            selection = expectation.book_retrieval
            if selection is None and len(available_books) > 1 and expectation.decision != "not_requested":
                failures.append(f"proposal {proposal.proposal_id} requires book retrieval expectations for multiple books")
            if selection is not None:
                required_books = set(selection.required_work_ids)
                optional_books = set(selection.optional_work_ids)
                if required_books | optional_books | set(selection.forbidden_work_ids) != available_books:
                    failures.append(f"proposal {proposal.proposal_id} book retrieval expectations must cover available books")
                evidence_books = {
                    item.evidence_id: {
                        record.work_id for record in evidence_by_id[item.evidence_id].accepted_runtime_records
                    }
                    for item in proposal.evidence
                    if item.evidence_id in evidence_by_id
                }
                permitted_books = set().union(*(
                    works for identity, works in evidence_books.items()
                    if identity in expectation.permitted_evidence_ids
                ))
                if not required_books <= permitted_books:
                    failures.append(f"proposal {proposal.proposal_id} requires inspectable evidence for every required book")
                if not optional_books <= permitted_books:
                    failures.append(f"proposal {proposal.proposal_id} requires inspectable evidence for every optional book")
                if set().union(*evidence_books.values()) - required_books - optional_books:
                    failures.append(f"proposal {proposal.proposal_id} cannot permit evidence from forbidden books")
                if any(
                    works & optional_books for identity, works in evidence_books.items()
                    if identity in expectation.required_evidence_ids
                ):
                    failures.append(f"proposal {proposal.proposal_id} optional book evidence cannot require citation")
            kinds = {item.evidence_id: item.kind for item in proposal.evidence}
            for alternative in expectation.evidence_alternatives:
                if any(kinds.get(item) != kinds.get(alternative.evidence_id)
                       for item in alternative.accepted_evidence_ids):
                    failures.append(
                        f"proposal {proposal.proposal_id} evidence alternatives must match "
                        f"the kind of {alternative.evidence_id}"
                    )
            if expectation.decision == "proposal":
                required = set(expectation.required_evidence_ids)
                required_kinds = {item.kind for item in proposal.evidence if item.evidence_id in required}
                if proposal.objective_id == CONNECTION_OBJECTIVE_ID and required_kinds != {"prop", "repository_text", "public_source"}:
                    failures.append(f"connection proposal {proposal.proposal_id} requires cited memory, book, and public evidence")
            if expectation.decision == "restraint" and not proposal.evidence:
                failures.append(f"weak connection proposal {proposal.proposal_id} requires inspectable insufficient evidence")
            if expectation.decision == "not_requested" and proposal.evidence:
                failures.append(f"personal reflection proposal {proposal.proposal_id} cannot declare evidence")
            if expectation.required_public_claims and not any(
                isinstance(item, PublicSourceEvidence) and item.evidence_id in expectation.required_evidence_ids
                for item in proposal.evidence
            ):
                failures.append(f"proposal {proposal.proposal_id} public claims require public citation evidence")
        if len(scene_proposals) > 1:
            scene_decisions = {proposal.connection.decision for proposal in scene_proposals if proposal.connection is not None}
            if len(scene_decisions) > 1:
                failures.append(f"Scene {scene.scene_id} has conflicting connection decisions")
            response_sets = [set(proposal.connection.acceptable_responses) for proposal in scene_proposals if proposal.connection is not None]
            if response_sets and not set.intersection(*response_sets):
                failures.append(f"Scene {scene.scene_id} has no jointly acceptable response")
        compiled.append(ValidatedConnectionScene(
            scene=scene,
            line=lines[scene.line_ids[0]],
            props=scene_props,
            source_setup=setup,
            evidence_by_id=evidence_by_id,
            proposals=scene_proposals,
        ))
    required_decisions = {
        CONNECTION_OBJECTIVE_ID: {"proposal", "restraint"},
        WEAK_EVIDENCE_OBJECTIVE_ID: {"restraint", "not_requested"},
    }
    for objective in connection_objectives:
        if not required_decisions[objective] <= decisions[objective]:
            failures.append(f"{objective} requires contrasting Scenes covering {sorted(required_decisions[objective])}")
    if failures:
        raise ConnectionContractError(failures)
    return ConnectionReplayPlan(backstory, ground_truth, selected, tuple(compiled))


def _resolve_book_evidence(
    evidence: RepositoryTextEvidence,
    setup: SceneSourceSetup | None,
    resolver: BookEvidenceResolver,
) -> ResolvedCorpusSpan:
    if setup is None or not setup.book_scopes:
        raise ValueError("book evidence requires trusted Scene book scope")
    for scope in setup.book_scopes:
        resolved = resolver.resolve_repository_evidence(scope.work_id, scope.book_version_id, evidence)
        if resolved is not None:
            if resolved.chapter_number > scope.safe_ceiling_chapter:
                raise ValueError("book evidence exceeds trusted Scene ceiling")
            return resolved
    raise ValueError("book evidence is not in the Scene's registered corpus")
