"""Dialect and code-mixed fairness for Muse's deterministic pre-model guards.

A Singapore-deployed reader may write Singlish, Indian English, or code-mixed
English; this must not make the language guard refuse them or the self-harm
detector miss them. Cases live in `evals/muse/dialect_fairness_cases.json` so
failures report clearly, per dialect, instead of one opaque parametrised diff.
"""

import json
from pathlib import Path

import pytest

from apps.backend.message_normalization import normalize_reader_message
from src.linger.orchestration.language_guard import detect_non_english
from src.linger.orchestration.self_harm_detection import detect_first_person_self_harm

CASES_PATH = Path(__file__).parent.parent / "evals" / "muse" / "dialect_fairness_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def _id(case: dict) -> str:
    return case["case_id"]


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_language_guard_outcome_matches_the_dialect_fixture(case: dict) -> None:
    normalized = normalize_reader_message(case["text"])
    refused = detect_non_english(normalized) is not None
    assert refused == case["language_refused"], (
        f"[{case['dialect']}] {case['case_id']}: expected language_refused="
        f"{case['language_refused']}, got {refused} for {case['text']!r}"
    )


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_self_harm_guard_outcome_matches_the_dialect_fixture(case: dict) -> None:
    normalized = normalize_reader_message(case["text"])
    matched = detect_first_person_self_harm(normalized)
    assert matched == case["self_harm"], (
        f"[{case['dialect']}] {case['case_id']}: expected self_harm="
        f"{case['self_harm']}, got {matched} for {case['text']!r}"
    )


def test_case_ids_are_unique_and_every_case_has_a_dialect_tag() -> None:
    ids = [case["case_id"] for case in CASES]
    assert len(ids) == len(set(ids)), "duplicate case_id in dialect_fairness_cases.json"
    for case in CASES:
        assert case.get("dialect"), f"{case['case_id']} is missing a dialect tag"
