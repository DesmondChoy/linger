"""Tests for the offline Sculptor-only memory search loop."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from tests.test_memory_loop_replay import (
    NIGHT_LINE,
    NIGHT_SCENE,
    NONE_LINE,
    NONE_SCENE,
    SETTINGS,
    _scenario,
    _sculptor,
    _validate,
)

with patch("src.linger.agents.build.build_model", return_value=TestModel()):
    from evals.synthetic_journals.offline_search_loop import (
        OfflineSearchPreregistration,
        OfflineSearchRun,
        render_summary,
        run_offline_search_loop,
        sign_flip_p_value,
        top_k_probability,
    )

NIGHT_VARIANTS = tuple(
    f"hosting moved thursdays tuesdays {suffix}"
    for suffix in ("night", "day", "evening", "week", "change")
)


def _preregistration(
    *,
    night_role: str = "improve",
    night_queries: tuple[str, ...] = (NIGHT_LINE, *NIGHT_VARIANTS),
    k: int = 1,
) -> OfflineSearchPreregistration:
    return OfflineSearchPreregistration(
        experiment="offline-sculptor-search-loop",
        registered_on=date(2026, 10, 1),
        query_source="Test queries.",
        k=k,
        alpha=0.05,
        non_inferiority_margin=0.1,
        required_repetitions=2,
        scenes=(
            {"scene_id": NIGHT_SCENE, "role": night_role, "queries": night_queries},
            {"scene_id": NONE_SCENE, "role": "report", "queries": (NONE_LINE,)},
        ),
    )


def _run(
    preregistration: OfflineSearchPreregistration,
    prompts: list[dict],
    **scenario: object,
) -> OfflineSearchRun:
    backstory, ground_truth = _scenario(**scenario)  # type: ignore[arg-type]
    _validate(backstory, ground_truth)
    return asyncio.run(
        run_offline_search_loop(
            backstory,
            ground_truth,
            preregistration,
            sculptor=_sculptor(prompts),
            settings=SETTINGS,
        )
    )


def test_top_k_probability_averages_over_every_tie_order() -> None:
    ranking = [(3, "a"), (2, "b"), (2, "c"), (2, "d"), (0, "e")]

    assert top_k_probability(ranking, frozenset({"a"}), 2) == 1.0
    assert top_k_probability(ranking, frozenset({"c"}), 2) == pytest.approx(1 / 3)
    assert top_k_probability(ranking, frozenset({"c", "d"}), 2) == pytest.approx(2 / 3)
    assert top_k_probability(ranking, frozenset({"b"}), 4) == 1.0
    assert top_k_probability(ranking, frozenset({"b"}), 1) == 0.0
    assert top_k_probability(ranking, frozenset({"e"}), 5) == 0.0
    assert top_k_probability(ranking, frozenset(), 5) == 0.0


def test_sign_flip_p_value_is_the_exact_one_sided_randomization_test() -> None:
    assert sign_flip_p_value([0.5] * 5) == pytest.approx(1 / 32)
    assert sign_flip_p_value([1.0, -1.0]) == pytest.approx(3 / 4)
    assert sign_flip_p_value([0.0, 0.0]) == 1.0
    assert sign_flip_p_value([-0.5] * 3) == 1.0


def test_a_summary_that_search_reaches_counts_for_both_sources_and_passes() -> None:
    prompts: list[dict] = []

    run = _run(_preregistration(), prompts)

    assert run.curation_review == "ablated"
    assert [(item.repetition, item.round, item.status) for item in run.curation] == [
        (repetition, round_number, "applied")
        for repetition in (1, 2)
        for round_number in (1, 2, 3)
    ]
    night = {
        (arm.repetition, arm.curation_rounds): arm
        for arm in run.arms
        if arm.scene_id == NIGHT_SCENE
    }
    assert set(night) == {(r, n) for r in (1, 2) for n in range(4)}
    for repetition in (1, 2):
        assert night[(repetition, 0)].query_recall == (0.5,) * 6
        assert night[(repetition, 2)].query_recall == (0.5,) * 6
        assert night[(repetition, 3)].query_recall == (0.5,) + (1.0,) * 5
    assert all(
        arm.query_recall == () and arm.mean_recall is None
        for arm in run.arms
        if arm.scene_id == NONE_SCENE
    )
    verdict, report = run.verdicts
    assert verdict.passed is True
    assert [item.p_value for item in verdict.repetitions] == [
        pytest.approx(1 / 32)
    ] * 2
    assert report.role == "report" and report.passed is None
    assert run.result == "positive"
    assert not any(
        variant in json.dumps(prompt) for prompt in prompts for variant in NIGHT_VARIANTS
    )
    assert "pass p=0.031" in render_summary(run)


def test_a_hidden_relevant_copy_is_reached_through_its_retrievable_copy() -> None:
    run = _run(
        _preregistration(
            night_queries=(NIGHT_LINE, "who did people sit beside"),
            k=5,
        ),
        [],
        night_relevant=("prop-copy-b",),
    )

    recall = sorted(
        (arm.repetition, arm.curation_rounds, arm.query_recall)
        for arm in run.arms
        if arm.scene_id == NIGHT_SCENE
    )
    assert [item[2][1] for item in recall] == [1.0] * 8


def test_an_unimproved_scene_is_not_positive() -> None:
    run = _run(_preregistration(night_queries=(NIGHT_LINE,)), [])

    assert run.verdicts[0].passed is False
    assert run.result == "not_positive"


@pytest.mark.parametrize(
    ("preregistration", "message"),
    [
        (_preregistration(night_queries=("not the line",)), "first query"),
        (_preregistration(night_role="hold"), "improve Scene"),
    ],
)
def test_preregistration_must_match_the_scenario(
    preregistration: OfflineSearchPreregistration, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _run(preregistration, [])
