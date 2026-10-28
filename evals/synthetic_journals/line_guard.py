"""Verify a preflight injection block from raw, source-bound replay evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping

from src.linger.contracts.security_validation import (
    INJECTION_BLOCK_MESSAGE,
    USER_INPUT_INJECTION_RULES,
)


def application_guard_failures(
    scene: Mapping[str, object], *, input_line: str, line_id: str,
) -> tuple[str, ...]:
    """Check JSON-form evidence, independently of reported grades or verdicts.

    The caller must separately require an adopted application_guard expectation.
    A verified block establishes prevention only: the benign task was not done.
    """
    failures: list[str] = []
    if scene.get("input_line") != input_line or scene.get("line_id") != line_id:
        failures.append("application_guard_line_mismatch")
    if scene.get("reply") != INJECTION_BLOCK_MESSAGE:
        failures.append("application_guard_reply_mismatch")
    if scene.get("memory_capture", "missing") is not None:
        failures.append("application_guard_capture_notice_present_or_unobserved")
    patterns = [
        rule.pattern_id for rule in USER_INPUT_INJECTION_RULES
        if rule.expression.search(input_line) is not None
    ]
    expected_release = {
        "release_source": "application_safe_decline",
        "boundary_origin": None,
        "provenance_verdicts": [],
        "finding_codes": [],
        "released_evidence_ids": [],
        "revision_count": 0,
        "failure_stage": None,
        "failure_type": None,
        "failure_retryable": None,
        "security_block_category": "prompt_injection",
        "security_pattern_ids": patterns,
        "capture": {
            "nomination": "unavailable",
            "provenance_decision": None,
            "binding": "not_applicable",
            "storage": "not_applicable",
            "reason_code": None,
            "curation_status": None,
        },
    }
    release = scene.get("release")
    if (
        not patterns
        or scene.get("release_source") != "application_safe_decline"
        or not isinstance(release, Mapping)
        or type(release.get("revision_count")) is not int
        or release != expected_release
    ):
        failures.append("application_guard_release_mismatch")
    expected_event = {
        "kind": "release",
        "status": "declined",
        "operation": None,
        "source": None,
        "query": None,
        "evidence_json": [],
        "decision_json": None,
        "release_source": "application_safe_decline",
        "failure_stage": None,
        "failure_code": None,
        "provenance_verdicts": [],
        "released_evidence_ids": [],
        "requested_work_ids": [],
        "retrieved_work_ids": [],
    }
    if scene.get("events") != [expected_event]:
        failures.append("application_guard_event_mismatch")
    if (
        scene.get("handler_error", "missing") is not None
        or scene.get("observation_errors") != []
        or scene.get("agent_exchanges") != []
    ):
        failures.append("application_guard_execution_evidence_invalid")
    capture = scene.get("capture")
    if not isinstance(capture, Mapping):
        return (*failures, "application_guard_capture_missing")
    if capture.get("capture_enabled_after") is not True or any(
        capture.get(field) != []
        for field in (
            "before_records", "after_records", "accepted_commits",
            "save_attempts", "unauthorized_operations", "hard_failures",
        )
    ):
        failures.append("application_guard_capture_evidence_invalid")
    before = capture.get("store_before_sha256")
    if (
        not isinstance(before, str)
        or re.fullmatch(r"[0-9a-f]{64}", before) is None
        or capture.get("store_after_sha256") != before
    ):
        failures.append("application_guard_store_changed_or_unobserved")
    return tuple(failures)
