"""Measure memory search before and after unreviewed Sculptor curation rounds.

This is an ablation of the memory loop. Sculptor is the only agent: each
round applies its proposal without Provenance curation review, and recall is
production memory search over a frozen, pre-registered query set, with no
chat turn. Results describe search reachability, not production behaviour.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
import tempfile
from collections.abc import Sequence
from datetime import date
from math import comb
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

import logfire
from opentelemetry.trace import format_trace_id
from pydantic import Field

from apps.backend.telemetry import configure_synthetic_evaluation_telemetry
from src.linger.agents.contracts import PromptFingerprint
from src.linger.agents.provenance.curation_models import CurationProvenanceReview
from src.linger.agents.serendipity.tools import MAX_RESULTS_PER_SOURCE, rank_memories
from src.linger.contracts.curation import CuratedMemory

from .adoption import GroundTruthAdoptionError, validate_ground_truth_adoption_files
from .memory_loop_replay import (
    CurationRoundObservation,
    _loop_scenes,
    _loop_settings,
    _Repetition,
    _retrievable_copy,
    _run_curation_round,
    _seed_repetition,
)
from .models import (
    CurationRecallLoop,
    GroundTruthAdoption,
    ProposedGroundTruth,
    StrictModel,
    SyntheticBackstory,
)
from .replay import (
    RUNTIME_PROMPT_FINGERPRINTS,
    RUNTIME_SYSTEM_VARIANT,
    GroundTruthStatus,
    evaluation_agents,
)
from .retrieval_replay import _RetrievalScene
from .validate_scenario import ScenarioValidationError, validate_scenario_files

PREREGISTRATION_FILE = "offline-search-preregistration.json"

SearchRole = Literal["improve", "hold", "report"]


class PreregisteredScene(StrictModel):
    """One Scene's declared expectation and frozen search queries."""

    scene_id: str
    role: SearchRole
    queries: tuple[str, ...] = Field(min_length=1)


class OfflineSearchPreregistration(StrictModel):
    """Measures and decision rule fixed before any treatment arm is observed."""

    experiment: Literal["offline-sculptor-search-loop"]
    registered_on: date
    query_source: str = Field(min_length=1)
    k: int = Field(ge=1, le=MAX_RESULTS_PER_SOURCE)
    alpha: float = Field(gt=0, lt=1)
    non_inferiority_margin: float = Field(ge=0, le=1)
    required_repetitions: int = Field(ge=1)
    scenes: tuple[PreregisteredScene, ...] = Field(min_length=1)


class SearchArm(StrictModel):
    """Tie-aware recall of one Scene's queries after some curation rounds."""

    scene_id: str
    repetition: int = Field(ge=1)
    curation_rounds: int = Field(ge=0)
    query_recall: tuple[float, ...]
    mean_recall: float | None


class RepetitionVerdict(StrictModel):
    """One repetition of a graded Scene against its pre-registered rule."""

    repetition: int = Field(ge=1)
    raw_mean_recall: float
    final_mean_recall: float
    worst_mean_recall: float
    p_value: float | None = None
    passed: bool


class SceneVerdict(StrictModel):
    """Whether a Scene met its role across repetitions."""

    scene_id: str
    role: SearchRole
    repetitions: tuple[RepetitionVerdict, ...]
    passed: bool | None


class OfflineSearchRun(StrictModel):
    """Search reachability on raw Props and after each unreviewed round."""

    artifact_schema_version: Literal["1"] = "1"
    content_classification: Literal["synthetic"] = "synthetic"
    curation_review: Literal["ablated"] = "ablated"
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    curation_rounds: int = Field(ge=1)
    repetitions: int = Field(ge=1)
    backstory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_status: GroundTruthStatus
    system_variant: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_prompt_fingerprints: tuple[PromptFingerprint, ...]
    preregistration: OfflineSearchPreregistration
    curation: tuple[CurationRoundObservation, ...]
    arms: tuple[SearchArm, ...]
    verdicts: tuple[SceneVerdict, ...]
    result: Literal["positive", "not_positive"]


class _UnreviewedApproval:
    """Allow every proposal, removing Provenance curation review."""

    name = "provenance"
    model = None
    model_settings = None

    async def run(self, prompt: str, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            output=CurationProvenanceReview(
                proposal_digest=json.loads(prompt)["proposal_digest"],
                decision="allow",
            ),
            new_messages=lambda: (),
        )


def top_k_probability(
    ranking: Sequence[tuple[int, str]],
    standing_ids: frozenset[str],
    k: int,
) -> float:
    """Chance that search returns any standing record, ties broken at random.

    Search returns at most k records with a positive score and breaks score
    ties by memory ID, which is arbitrary with respect to content. Averaging
    over every tie order follows McSherry and Najork (ECIR 2008).
    """

    scores = [score for score, memory_id in ranking if memory_id in standing_ids]
    best = max(scores, default=0)
    if best <= 0:
        return 0.0
    above = sum(score > best for score, _ in ranking)
    tied = sum(score == best for score, _ in ranking)
    standing_tied = scores.count(best)
    slots = k - above
    if slots <= 0:
        return 0.0
    if slots >= tied:
        return 1.0
    return 1 - comb(tied - standing_tied, slots) / comb(tied, slots)


def sign_flip_p_value(differences: Sequence[float]) -> float:
    """Exact one-sided paired randomization test that the mean rose.

    Smucker, Allan and Carterette (CIKM 2007) recommend the randomization
    test for paired per-query IR comparisons.
    """

    nonzero = [value for value in differences if abs(value) > 1e-12]
    if not nonzero:
        return 1.0
    observed = sum(nonzero)
    outcomes = [
        sum(sign * value for sign, value in zip(signs, nonzero, strict=True))
        for signs in itertools.product((1, -1), repeat=len(nonzero))
    ]
    return sum(total >= observed - 1e-12 for total in outcomes) / len(outcomes)


def _standing_ids(
    prop_id: str,
    repetition: _Repetition,
    view: dict[str, CuratedMemory],
    canonical_of: dict[str, str],
) -> frozenset[str]:
    """Retrieval records that put this Prop's content in front of recall.

    A Prop counts as reached through itself, its retrievable copy when it is
    hidden, or a derived summary of either. A topic group does not count: its
    searchable text is only a label.
    """

    sources = {
        repetition.memory_ids[prop_id],
        repetition.memory_ids[_retrievable_copy(prop_id, canonical_of)],
    }
    return frozenset(
        item.memory_id
        for item in view.values()
        if (item.kind == "original" and item.memory_id in sources)
        or (item.kind == "derived_summary" and sources & set(item.source_memory_ids))
    )


def _search_arm(
    scene: _RetrievalScene,
    registered: PreregisteredScene,
    repetition: _Repetition,
    *,
    k: int,
) -> SearchArm:
    view = repetition.view()
    canonical_of = repetition.canonical_of()
    standing = [
        _standing_ids(prop_id, repetition, view, canonical_of)
        for prop_id in scene.relevant_prop_ids
    ]
    recall: list[float] = []
    for query in registered.queries if standing else ():
        ranking = [
            (score, item.memory_id)
            for score, item in rank_memories(query, tuple(view.values()))
        ]
        recall.append(
            sum(top_k_probability(ranking, ids, k) for ids in standing) / len(standing)
        )
    query_recall = tuple(recall)
    return SearchArm(
        scene_id=scene.scene_id,
        repetition=repetition.number,
        curation_rounds=repetition.rounds_done,
        query_recall=query_recall,
        mean_recall=(
            sum(query_recall) / len(query_recall) if query_recall else None
        ),
    )


def scene_verdict(
    registered: PreregisteredScene,
    arms: Sequence[SearchArm],
    preregistration: OfflineSearchPreregistration,
) -> SceneVerdict:
    """Apply the pre-registered rule to every repetition of one Scene."""

    if registered.role == "report":
        return SceneVerdict(
            scene_id=registered.scene_id,
            role="report",
            repetitions=(),
            passed=None,
        )
    by_repetition: dict[int, list[SearchArm]] = {}
    for arm in arms:
        by_repetition.setdefault(arm.repetition, []).append(arm)
    verdicts: list[RepetitionVerdict] = []
    for number, observed in sorted(by_repetition.items()):
        ordered = sorted(observed, key=lambda arm: arm.curation_rounds)
        raw, final = ordered[0], ordered[-1]
        if raw.mean_recall is None or final.mean_recall is None:
            raise ValueError(f"{registered.scene_id} has no relevant Prop to grade")
        worst = min(arm.mean_recall or 0.0 for arm in ordered)
        if registered.role == "improve":
            p_value = sign_flip_p_value(
                [
                    after - before
                    for before, after in zip(
                        raw.query_recall, final.query_recall, strict=True
                    )
                ]
            )
            passed = (
                final.mean_recall > raw.mean_recall
                and p_value <= preregistration.alpha
            )
        else:
            p_value = None
            passed = worst >= raw.mean_recall - preregistration.non_inferiority_margin
        verdicts.append(
            RepetitionVerdict(
                repetition=number,
                raw_mean_recall=raw.mean_recall,
                final_mean_recall=final.mean_recall,
                worst_mean_recall=worst,
                p_value=p_value,
                passed=passed,
            )
        )
    passed_count = sum(item.passed for item in verdicts)
    required = (
        preregistration.required_repetitions
        if registered.role == "improve"
        else len(verdicts)
    )
    return SceneVerdict(
        scene_id=registered.scene_id,
        role=registered.role,
        repetitions=tuple(verdicts),
        passed=passed_count >= required,
    )


def _registered_scenes(
    scenes: Sequence[_RetrievalScene],
    preregistration: OfflineSearchPreregistration,
) -> tuple[PreregisteredScene, ...]:
    registered = preregistration.scenes
    if tuple(item.scene_id for item in registered) != tuple(
        scene.scene_id for scene in scenes
    ):
        raise ValueError("pre-registration must list every Scene in Scenario order")
    for scene, item in zip(scenes, registered, strict=True):
        if item.queries[0] != scene.line:
            raise ValueError(f"{scene.scene_id}: the first query must be its Line")
        if item.role != "report" and not scene.relevant_prop_ids:
            raise ValueError(f"{scene.scene_id}: a graded Scene needs a relevant Prop")
    if not any(item.role == "improve" for item in registered):
        raise ValueError("pre-registration needs at least one improve Scene")
    return registered


async def run_offline_search_loop(
    backstory: SyntheticBackstory,
    ground_truth: ProposedGroundTruth,
    preregistration: OfflineSearchPreregistration,
    *,
    adoption: GroundTruthAdoption | None = None,
    sculptor: Any | None = None,
    settings: CurationRecallLoop | None = None,
) -> OfflineSearchRun:
    """Search every frozen query on raw Props and after each cumulative round.

    Each repetition starts from identical Props, so repetitions sample only
    Sculptor's choices. Sculptor never sees a query or a Line.
    """

    scenes = _loop_scenes(backstory, ground_truth)
    registered = _registered_scenes(scenes, preregistration)
    props = scenes[0].props
    loop_settings = settings or _loop_settings()
    if sculptor is None:
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    curation_agents: dict[str, Any] = {"provenance": _UnreviewedApproval()}
    if sculptor is not None:
        curation_agents["sculptor"] = sculptor

    run_id = uuid4().hex
    arms: list[SearchArm] = []
    curation: list[CurationRoundObservation] = []
    with (
        tempfile.TemporaryDirectory(prefix="linger-offline-search-") as directory,
        logfire.span(
            "offline_search_loop",
            run_id=run_id,
            curation_review="ablated",
            content_classification="synthetic",
        ) as span,
    ):
        for number in range(1, loop_settings.repetitions + 1):
            repetition = _seed_repetition(
                number,
                props,
                root=Path(directory),
                account_id=(
                    f"synthetic-eval:{backstory.backstory.evaluation_account_id}"
                    f":{run_id}"
                ),
            )
            while True:
                arms.extend(
                    _search_arm(scene, item, repetition, k=preregistration.k)
                    for scene, item in zip(scenes, registered, strict=True)
                )
                if repetition.rounds_done == loop_settings.curation_rounds:
                    break
                curation.append(
                    await _run_curation_round(
                        repetition, curation_agents=curation_agents
                    )
                )
        trace_id = format_trace_id(span.get_span_context().trace_id)

    verdicts = tuple(
        scene_verdict(
            item,
            [arm for arm in arms if arm.scene_id == item.scene_id],
            preregistration,
        )
        for item in registered
    )
    return OfflineSearchRun(
        run_id=run_id,
        trace_id=trace_id,
        curation_rounds=loop_settings.curation_rounds,
        repetitions=loop_settings.repetitions,
        backstory_sha256=ground_truth.backstory_sha256,
        dataset_version=(
            adoption.adopted_ground_truth_identity
            if adoption is not None
            else ground_truth.backstory_sha256
        ),
        ground_truth_status=(
            adoption.ground_truth_status
            if adoption is not None
            else ground_truth.ground_truth_status
        ),
        system_variant=RUNTIME_SYSTEM_VARIANT,
        runtime_prompt_fingerprints=RUNTIME_PROMPT_FINGERPRINTS,
        preregistration=preregistration,
        curation=tuple(curation),
        arms=tuple(arms),
        verdicts=verdicts,
        result=(
            "positive"
            if all(item.passed is not False for item in verdicts)
            else "not_positive"
        ),
    )


def render_summary(run: OfflineSearchRun) -> str:
    """Mean recall per Scene, repetition, and round, then each verdict."""

    rounds = range(run.curation_rounds + 1)
    lines = [
        f"Unreviewed curation ablation, run {run.run_id[:8]}: {run.result}",
        "scene | role | rep | " + " | ".join(f"r{n}" for n in rounds) + " | verdict",
    ]
    by_key = {
        (arm.scene_id, arm.repetition, arm.curation_rounds): arm for arm in run.arms
    }
    for verdict in run.verdicts:
        for repetition in range(1, run.repetitions + 1):
            cells = []
            for n in rounds:
                mean = by_key[(verdict.scene_id, repetition, n)].mean_recall
                cells.append("-" if mean is None else f"{mean:.2f}")
            outcome = next(
                (
                    ("pass" if item.passed else "fail")
                    + ("" if item.p_value is None else f" p={item.p_value:.3f}")
                    for item in verdict.repetitions
                    if item.repetition == repetition
                ),
                "reported",
            )
            lines.append(
                f"{verdict.scene_id} | {verdict.role} | {repetition} | "
                + " | ".join(cells)
                + f" | {outcome}"
            )
    for item in run.curation:
        lines.append(
            f"repetition {item.repetition} round {item.round}: {item.status}"
            + (f" {item.action} {list(item.source_prop_ids)}" if item.action else "")
            + (f" ({item.failure})" if item.failure else "")
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backstory", type=Path)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--adoption", type=Path)
    parser.add_argument(
        "--preregistration",
        type=Path,
        help=f"defaults to {PREREGISTRATION_FILE} beside the Backstory",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.adoption is None:
            backstory, ground_truth = validate_scenario_files(
                args.backstory, args.ground_truth
            )
            adoption = None
        else:
            backstory, ground_truth, adoption = validate_ground_truth_adoption_files(
                args.backstory, args.ground_truth, args.adoption
            )
        preregistration = OfflineSearchPreregistration.model_validate_json(
            (
                args.preregistration or args.backstory.parent / PREREGISTRATION_FILE
            ).read_text(encoding="utf-8")
        )
        result = asyncio.run(
            run_offline_search_loop(
                backstory, ground_truth, preregistration, adoption=adoption
            )
        )
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered, encoding="utf-8")
            print(render_summary(result), end="")
    except (
        OSError,
        GroundTruthAdoptionError,
        ScenarioValidationError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"EVALUATION_RUN_ERROR={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
