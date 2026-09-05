"""Compile synthetic book Ground truth into one trusted replay plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .book_evidence import BookEvidenceResolver, ResolvedCorpusSpan
from .models import (
    BookSceneFacts,
    GroundedBookExpectation,
    GroundTruthProposal,
    LibrarianInferredBookScope,
    Prop,
    ProposedGroundTruth,
    ReaderConfirmedBookScope,
    Scene,
    SpoilerBoundaryBookExpectation,
    SyntheticBackstory,
)

BOOK_OBJECTIVE_IDS = frozenset(
    {"grounded_book_reflection", "spoiler_boundary_clarification"}
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class BookContractError(ValueError):
    """One or more canonical book-contract checks failed."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = tuple(failures)
        super().__init__("; ".join(failures))


@dataclass(frozen=True)
class ValidatedBookScene:
    scene: Scene
    line_id: str
    line: str
    props: tuple[Prop, ...]
    facts: BookSceneFacts | None
    safe_ceiling_chapter: int | None
    evidence_by_id: dict[str, ResolvedCorpusSpan]
    proposals: tuple[GroundTruthProposal, ...]


@dataclass(frozen=True)
class BookReplayPlan:
    backstory: SyntheticBackstory
    ground_truth: ProposedGroundTruth
    objective_ids: frozenset[str]
    scenes: tuple[ValidatedBookScene, ...]


def compile_book_replay_plan(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> BookReplayPlan:
    """Resolve one book package into the only representation replay may consume."""

    try:
        backstory = SyntheticBackstory.model_validate_json(backstory.model_dump_json())
        ground_truth = ProposedGroundTruth.model_validate_json(
            ground_truth.model_dump_json()
        )
    except ValidationError as error:
        raise BookContractError([str(error)]) from error
    selected = frozenset(backstory.objective_ids)
    if not selected or not selected <= BOOK_OBJECTIVE_IDS:
        raise BookContractError(
            ["book replay accepts grounded, spoiler, or both book Objectives"]
        )
    failures: list[str] = []
    resolver = BookEvidenceResolver(repository_root)
    if backstory.run_configuration_ids:
        failures.append("book replay accepts no run configuration")
    if backstory.offline_inputs:
        failures.append("book replay accepts Lines, not offline inputs")

    scenes = {scene.scene_id: scene for scene in backstory.scenes}
    props = {prop.prop_id: prop for prop in backstory.props}
    lines = {line.line_id: line for line in backstory.lines}
    facts_by_scene = {facts.scene_id: facts for facts in ground_truth.book_scene_facts}
    expected_proposals = {
        (scene.scene_id, objective_id)
        for scene in backstory.scenes
        for objective_id in scene.objective_ids
    }
    actual_proposals = {
        (proposal.scene_id, proposal.objective_id)
        for proposal in ground_truth.proposals
    }
    if actual_proposals != expected_proposals:
        raise BookContractError(
            ["book proposal coverage must exactly match Scene Objectives"]
        )
    proposals_by_scene: dict[str, list[GroundTruthProposal]] = {}
    for proposal in ground_truth.proposals:
        if proposal.objective_id in BOOK_OBJECTIVE_IDS:
            proposals_by_scene.setdefault(proposal.scene_id, []).append(proposal)

    extra_facts = set(facts_by_scene) - set(scenes)
    if extra_facts:
        failures.append(f"book facts reference unknown Scenes: {sorted(extra_facts)}")

    compiled: list[ValidatedBookScene] = []
    for scene in sorted(backstory.scenes, key=lambda item: item.order):
        scene_objectives = frozenset(scene.objective_ids)
        if not scene_objectives <= BOOK_OBJECTIVE_IDS:
            failures.append(
                f"book replay Scene {scene.scene_id} contains unsupported Objectives"
            )
            continue
        if not scene.fresh_session:
            failures.append(
                f"book replay Scene {scene.scene_id} must use a fresh session"
            )
        for prop_id in scene.prop_ids:
            lifecycle = next(
                item
                for item in props[prop_id].lifecycle
                if item.scene_id == scene.scene_id
            )
            if lifecycle.state != "active":
                failures.append(
                    f"book replay Scene {scene.scene_id} requires active Prop {prop_id}"
                )
        if scene.offline_input_ids or len(scene.line_ids) != 1:
            failures.append(
                f"book replay Scene {scene.scene_id} requires one Line and no offline input"
            )
            continue
        line = lines.get(scene.line_ids[0])
        if line is None or line.order != 1:
            failures.append(
                f"book replay Scene {scene.scene_id} Line must have order 1"
            )
            continue

        scene_proposals = tuple(
            sorted(
                proposals_by_scene.get(scene.scene_id, ()),
                key=lambda item: scene.objective_ids.index(item.objective_id),
            )
        )
        facts = facts_by_scene.get(scene.scene_id)
        resolved: dict[str, ResolvedCorpusSpan] = {}
        ceiling: int | None = None
        if facts is not None:
            failures.extend(_validate_scene_facts(facts, scene, props))
            from .validate_package import _validate_span

            for span in facts.basis_spans:
                failures.extend(_validate_span(span, scene, props, lines, {}))
            try:
                _, catalog = resolver.catalog(
                    facts.scope.work_id, facts.scope.book_version_id
                )
                if (
                    isinstance(facts.scope, ReaderConfirmedBookScope)
                    and facts.scope.safe_ceiling_chapter > catalog["chapter_count"]
                ):
                    failures.append(f"Scene {scene.scene_id} ceiling exceeds corpus")
            except (OSError, ValueError) as error:
                failures.append(f"Scene {scene.scene_id} corpus integrity: {error}")
            for evidence in facts.evidence:
                try:
                    resolved[evidence.evidence_id] = resolver.resolve(
                        facts.scope.work_id, facts.scope.book_version_id, evidence
                    )
                except (OSError, ValueError, KeyError, TypeError) as error:
                    failures.append(
                        f"book Scene {scene.scene_id} evidence {evidence.evidence_id} "
                        f"is invalid: {error}"
                    )
            if isinstance(facts.scope, ReaderConfirmedBookScope):
                ceiling = facts.scope.safe_ceiling_chapter
            elif isinstance(facts.scope, LibrarianInferredBookScope):
                supporting = [
                    resolved.get(evidence_id)
                    for evidence_id in facts.scope.supporting_evidence_ids
                ]
                if None in supporting:
                    missing = sorted(
                        set(facts.scope.supporting_evidence_ids) - set(resolved)
                    )
                    failures.append(
                        f"book Scene {scene.scene_id} references missing supporting "
                        f"evidence: {missing}"
                    )
                elif supporting:
                    ceiling = max(item.chapter_number for item in supporting if item)

        failures.extend(
            _validate_scene_proposals(
                scene,
                scene_proposals,
                facts,
                resolved,
                ceiling,
            )
        )
        compiled.append(
            ValidatedBookScene(
                scene=scene,
                line_id=line.line_id,
                line=line.text,
                props=tuple(props[prop_id] for prop_id in scene.prop_ids),
                facts=facts,
                safe_ceiling_chapter=ceiling,
                evidence_by_id=resolved,
                proposals=scene_proposals,
            )
        )

    from .validate_package import _validate_pairing

    for case in compiled:
        for proposal in case.proposals:
            if proposal.pairing is None:
                failures.append(
                    f"proposal {proposal.proposal_id} requires a Scene pairing"
                )
            else:
                failures.extend(
                    _validate_pairing(proposal, case.scene, scenes, lines, {})
                )
                partner = next(
                    (
                        item
                        for item in compiled
                        if item.scene.scene_id == proposal.pairing.paired_scene_id
                    ),
                    None,
                )
                if (
                    partner is None
                    or proposal.objective_id not in partner.scene.objective_ids
                ):
                    failures.append(
                        f"proposal {proposal.proposal_id} must pair the same Objective"
                    )
                elif isinstance(proposal.book_expectation, GroundedBookExpectation):
                    other = next(
                        item
                        for item in partner.proposals
                        if item.objective_id == proposal.objective_id
                    )
                    if (
                        other.book_expectation.retrieval
                        == proposal.book_expectation.retrieval
                    ):
                        failures.append(
                            f"proposal {proposal.proposal_id} must pair opposite retrieval behavior"
                        )
                elif (
                    case.facts
                    and partner.facts
                    and case.facts.scope.kind == partner.facts.scope.kind
                ):
                    failures.append(
                        f"proposal {proposal.proposal_id} must pair inference and clarification"
                    )
    failures.extend(_coverage_failures(selected, tuple(compiled)))
    if failures:
        raise BookContractError(failures)
    return BookReplayPlan(
        backstory=backstory,
        ground_truth=ground_truth,
        objective_ids=selected,
        scenes=tuple(compiled),
    )


def _validate_scene_facts(
    facts: BookSceneFacts,
    scene: Scene,
    props: dict[str, Prop],
) -> list[str]:
    failures: list[str] = []
    scope = facts.scope
    if isinstance(scope, ReaderConfirmedBookScope):
        if facts.basis_spans:
            failures.append(
                f"reader-confirmed Scene {scene.scene_id} cannot declare inference spans"
            )
        return failures

    if not facts.basis_spans:
        failures.append(f"book Scene {scene.scene_id} requires exact inference spans")
    authorised = set(scope.authorised_prop_ids)
    unknown = authorised - set(scene.prop_ids)
    if unknown:
        failures.append(
            f"book Scene {scene.scene_id} authorises Props outside the Scene: {sorted(unknown)}"
        )
    prop_spans = {
        span.source_id for span in facts.basis_spans if span.source_kind == "prop"
    }
    if authorised - prop_spans:
        failures.append(
            f"book Scene {scene.scene_id} lacks exact spans for authorised Props: "
            f"{sorted(authorised - prop_spans)}"
        )
    if not any(span.source_kind == "line" for span in facts.basis_spans):
        failures.append(f"book Scene {scene.scene_id} requires an exact Line span")
    for prop_id in authorised & set(scene.prop_ids):
        prop = props.get(prop_id)
        if prop is None:
            continue
        lifecycle = next(
            item for item in prop.lifecycle if item.scene_id == scene.scene_id
        )
        if lifecycle.state != "active":
            failures.append(
                f"book Scene {scene.scene_id} authorised Prop {prop_id} is not active"
            )
    return failures


def _validate_scene_proposals(
    scene: Scene,
    proposals: tuple[GroundTruthProposal, ...],
    facts: BookSceneFacts | None,
    evidence: dict[str, ResolvedCorpusSpan],
    ceiling: int | None,
) -> list[str]:
    failures: list[str] = []
    if {proposal.objective_id for proposal in proposals} != set(scene.objective_ids):
        failures.append(f"book Scene {scene.scene_id} proposal coverage is incomplete")
        return failures
    for proposal in proposals:
        expected = proposal.book_expectation
        if isinstance(expected, GroundedBookExpectation):
            if expected.retrieval == "required":
                if facts is None or ceiling is None:
                    failures.append(
                        f"grounded proposal {proposal.proposal_id} requires bounded book facts"
                    )
                missing = set(expected.permitted_evidence_ids) - set(evidence)
                if missing:
                    failures.append(
                        f"grounded proposal {proposal.proposal_id} references missing evidence: "
                        f"{sorted(missing)}"
                    )
                if ceiling is not None:
                    too_late = sorted(
                        evidence_id
                        for evidence_id in expected.permitted_evidence_ids
                        if evidence_id in evidence
                        and evidence[evidence_id].chapter_number > ceiling
                    )
                    if too_late:
                        failures.append(
                            f"grounded proposal {proposal.proposal_id} permits evidence "
                            f"after the safe ceiling: {too_late}"
                        )
            elif facts is not None:
                failures.append(
                    f"no-retrieval proposal {proposal.proposal_id} shares a route-dependent Scene"
                )
        elif isinstance(expected, SpoilerBoundaryBookExpectation):
            if facts is None:
                failures.append(
                    f"spoiler proposal {proposal.proposal_id} requires book Scene facts"
                )
                continue
            if isinstance(facts.scope, ReaderConfirmedBookScope):
                failures.append(
                    f"spoiler proposal {proposal.proposal_id} requires inference or clarification, not reader-confirmed scope"
                )
            missing = set(expected.forbidden_later_evidence_ids) - set(evidence)
            if missing:
                failures.append(
                    f"spoiler proposal {proposal.proposal_id} references missing evidence: "
                    f"{sorted(missing)}"
                )
            if ceiling is not None:
                not_later = sorted(
                    evidence_id
                    for evidence_id in expected.forbidden_later_evidence_ids
                    if evidence_id in evidence
                    and evidence[evidence_id].chapter_number <= ceiling
                )
                if not_later:
                    failures.append(
                        f"spoiler proposal {proposal.proposal_id} has forbidden evidence "
                        f"at or before the safe ceiling: {not_later}"
                    )
    return failures


def _coverage_failures(
    selected: frozenset[str],
    scenes: tuple[ValidatedBookScene, ...],
) -> list[str]:
    failures: list[str] = []
    expectations = [
        proposal.book_expectation for scene in scenes for proposal in scene.proposals
    ]
    if "grounded_book_reflection" in selected:
        retrieval = {
            expected.retrieval
            for expected in expectations
            if isinstance(expected, GroundedBookExpectation)
        }
        if retrieval != {"required", "not_required"}:
            failures.append(
                "grounded book replay requires retrieval-required and no-retrieval Scenes"
            )
    if "spoiler_boundary_clarification" in selected:
        scope_kinds = {
            scene.facts.scope.kind
            for scene in scenes
            if scene.facts is not None
            and any(
                proposal.objective_id == "spoiler_boundary_clarification"
                for proposal in scene.proposals
            )
        }
        if not {"librarian_inferred", "clarification"} <= scope_kinds:
            failures.append("spoiler replay requires inferred and clarification Scenes")
    if selected == BOOK_OBJECTIVE_IDS and not any(
        set(scene.scene.objective_ids) == BOOK_OBJECTIVE_IDS
        and scene.facts is not None
        and scene.facts.scope.kind == "librarian_inferred"
        for scene in scenes
    ):
        failures.append("combined book replay requires one shared inferred Scene")
    return failures
