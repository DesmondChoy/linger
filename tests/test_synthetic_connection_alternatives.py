"""An accepted alternative satisfies one evidence item's inspection and citation."""

import hashlib
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from evals.synthetic_journals.connection_replay import grade_connection_scene
from evals.synthetic_journals.validate_scenario import ScenarioValidationError
from tests.test_synthetic_connection_multibook import (
    ROOT, _selected_evidence_decision, multibook_documents, multibook_events,
)
from tests.test_synthetic_connection_replay import response
from tests.test_synthetic_connection_scenario import validate_documents

ALTERNATIVE_QUOTE = "one hour more or less makes very little\ndifference."


def documents(*, alternative=True, kind=None):
    from src.linger.corpus.registry import CORPORA

    content, labels = multibook_documents()
    proposal = labels["proposals"][0]
    path = CORPORA["pg500"].root / "chapters/30-chapter-30.md"
    raw = path.read_bytes()
    start = raw.decode().index(ALTERNATIVE_QUOTE)
    identity = f"{proposal['proposal_id']}-pg500-delay"
    proposal["evidence"].append({
        "kind": "repository_text", "evidence_id": identity,
        "repository_path": str(path.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "start_codepoint": start, "end_codepoint": start + len(ALTERNATIVE_QUOTE),
        "text": ALTERNATIVE_QUOTE,
    })
    expectation = proposal["connection"]
    expectation["permitted_evidence_ids"].append(identity)
    if alternative:
        target = kind or f"{proposal['proposal_id']}-pg500"
        expectation["evidence_alternatives"] = [
            {"evidence_id": target, "accepted_evidence_ids": [identity]},
        ]
    return content, labels, proposal["proposal_id"]


def cited_events(scene, primary):
    events = []
    for event in multibook_events(scene):
        records = [json.loads(item) for item in event.evidence_json]
        if event.source == "book_corpus" and any(
            record["evidence_id"] == primary for record in records
        ):
            continue
        events.append(event)
    ids = tuple(json.loads(item)["evidence_id"] for event in events for item in event.evidence_json)
    return [
        replace(event, status="proposal", decision_json=_selected_evidence_decision(ids))
        if event.kind == "discovery"
        else replace(event, released_evidence_ids=ids)
        if event.kind == "release"
        else event
        for event in events
    ]


def primary_record(scene, proposal_id):
    return scene.evidence_by_id[f"{proposal_id}-pg500"].accepted_runtime_records[0].evidence_id


def test_citing_only_the_accepted_alternative_satisfies_the_required_passage():
    content, labels, proposal_id = documents()
    scene = validate_documents(content, labels, ROOT).scenes[0]
    events = cited_events(scene, primary_record(scene, proposal_id))
    grades = grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
    assert all(not grade.failures for grade in grades)


def test_without_the_alternative_the_same_run_misses_the_required_passage():
    content, labels, proposal_id = documents(alternative=False)
    scene = validate_documents(content, labels, ROOT).scenes[0]
    events = cited_events(scene, primary_record(scene, proposal_id))
    grade, = [item for item in grade_connection_scene(scene, response(), events, {"memory": "memory-runtime"})
              if item.proposal_id == proposal_id]
    assert "required_source_not_inspected" in grade.failures
    assert f"missing_required_citation:{proposal_id}-pg500" in grade.failures


@pytest.mark.parametrize("mutation, message", [
    ("unpermitted", "must name permitted evidence"),
    ("self", "its own alternative"),
    ("kind", "must match the kind"),
])
def test_alternatives_must_be_permitted_distinct_and_of_the_same_kind(mutation, message):
    content, labels, proposal_id = documents()
    expectation = labels["proposals"][0]["connection"]
    alternative = expectation["evidence_alternatives"][0]
    if mutation == "unpermitted":
        expectation["permitted_evidence_ids"].remove(alternative["accepted_evidence_ids"][0])
    elif mutation == "self":
        alternative["accepted_evidence_ids"] = [alternative["evidence_id"]]
    else:
        memory = next(item["evidence_id"] for item in labels["proposals"][0]["evidence"]
                      if item["kind"] == "prop")
        alternative["evidence_id"] = memory
    with pytest.raises((ValidationError, ScenarioValidationError), match=message):
        validate_documents(content, labels, ROOT)
