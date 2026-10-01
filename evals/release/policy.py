"""Publication routing over complete, adopted automated evidence."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any


# Failure names are tied to the runner and Objective that define their meaning.
# Every other failure, including new grader codes, remains a release blocker.
_BEHAVIORAL_FAILURES = {
    ("retrieval_replay", "longitudinal_memory_retrieval"): frozenset({
        "relevant_prop_not_retrieved", "relevant_prop_not_cited", "distractor_prop_cited",
    }),
    ("book_replay", "grounded_book_reflection"): frozenset({
        "required_grounding_evidence_not_retrieved", "grounded_response_released_no_evidence",
        "response_cited_no_permitted_evidence", "exact_quotation_missing_or_unreleased",
    }),
    ("connection_replay", "cross_source_tentative_connection"): frozenset({
        "connection_decision_mismatch", "required_book_not_searched", "required_book_not_retrieved",
        "missing_required_citation",
    }),
}


def behavioral_failure(runner: str, objective_ids: list[str], detail: str) -> bool:
    """Only recognized ordinary quality failures can reach publication review."""
    if len(objective_ids) != 1:
        return False
    key = (runner.removeprefix("evals.synthetic_journals."), objective_ids[0])
    code, separator, evidence_id = detail.partition(":")
    if code not in _BEHAVIORAL_FAILURES.get(key, ()):
        return False
    if code in {"exact_quotation_missing_or_unreleased", "missing_required_citation"}:
        return bool(separator and evidence_id and not any(character.isspace() for character in evidence_id))
    return not separator


def parse_threshold(value: str | float | int) -> Decimal:
    """Keep the comparison exact, including thresholds entered as decimals."""
    try:
        threshold = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("auto-publish-threshold must be a finite number from 0 to 100.") from error
    if not threshold.is_finite() or not 0 <= threshold <= 100:
        raise ValueError("auto-publish-threshold must be a finite number from 0 to 100.")
    return threshold


def publication_decision(
    *, judgments_passed: int, judgments_total: int, complete: bool, blocked: bool,
    auto_publish_enabled: bool = False, threshold: str | float | int = "95",
) -> dict[str, Any]:
    """An opted-in automated score is never a semantic safety certification."""
    limit = parse_threshold(threshold)
    if type(auto_publish_enabled) is not bool:
        raise ValueError("auto_publish_enabled must be a boolean.")
    valid_counts = (
        type(judgments_total) is int and type(judgments_passed) is int
        and judgments_total > 0 and 0 <= judgments_passed <= judgments_total
    )
    percentage = Decimal(judgments_passed) * 100 / judgments_total if valid_counts else None
    if blocked or not complete or not valid_counts:
        route, reason = "blocked", "Safety, execution, or complete adopted evidence requirements were not met."
    elif not auto_publish_enabled:
        route, reason = "manual", "Automatic publishing is disabled; maintainer approval is required."
    elif Fraction(judgments_passed * 100, judgments_total) > Fraction(limit):
        route, reason = "automatic", "Complete automated evidence is strictly above the configured threshold."
    else:
        route, reason = "manual", "The automated pass percentage is at or below the configured threshold."
    return {
        "route": route, "reason": reason, "auto_publish_enabled": auto_publish_enabled,
        "threshold": str(limit), "comparison": "strictly_greater_than",
        "score_scope": "adopted deterministic judgments",
        "semantic_assessment": "not_automatically_graded",
        "judgments_passed": judgments_passed, "judgments_total": judgments_total,
        "automated_pass_percentage": float(percentage) if percentage is not None else None,
    }
