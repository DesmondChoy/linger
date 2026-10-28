"""Extra book passages stay quality failures only within verified reading authority."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from apps.backend.librarian import Librarian
from evals.synthetic_journals.connection_contract import compile_connection_replay_plan
from evals.synthetic_journals.connection_replay import _authorized_book_extras, grade_connection_scene
from evals.synthetic_journals.models import BookRetrievalExpectation, ProposedGroundTruth, SyntheticBackstory
from src.linger.evaluation_transcript import ConnectionEvaluationEvent
from tests.test_synthetic_connection_replay import response, source_events


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "synthetic-journal-evaluation/scenarios/cross-source-connections-and-restraint--muse-librarian-serendipity-provenance--2026-09-12"
PIGEON = "pg11-v01b38ea4-ch05-ln1179-1219"
EARLIER = "pg11-v01b38ea4-ch01-ln0231-0256"


@pytest.fixture(scope="module")
def plan():
    return compile_connection_replay_plan(
        SyntheticBackstory.model_validate_json((SCENARIO / "backstory.json").read_text()),
        ProposedGroundTruth.model_validate_json((SCENARIO / "ground-truth.json").read_text()),
    )


def book_record(identity=PIGEON):
    record = Librarian().fetch_by_id(identity)
    assert record is not None
    return {
        "evidence_id": record.evidence_id, "work_id": record.work_id,
        "book_version_id": record.book_version_id, "chapter_id": record.chapter_id,
        "chapter": record.chapter_number, "part_id": record.part_id,
        "source_kind": "book_corpus", "trust_level": "canonical",
        "location": record.location, "source_sha256": record.source_sha256,
        "source_lines": list(record.source_lines), "excerpt": record.text,
    }


def grade_with_extras(scene, extras, *, cite=True, select=True):
    events = list(source_events(scene))
    expected_ids = [json.loads(event.evidence_json[0])["evidence_id"] for event in events]
    for record in extras.values():
        if record is not None:
            events.append(ConnectionEvaluationEvent(
                kind="search", status="evidence_found", source=record["source_kind"],
                evidence_json=(json.dumps(record),),
            ))
    events.extend((
        ConnectionEvaluationEvent(
            kind="discovery", status="gathered", decision_json=json.dumps({
                "status": "gathered", "evidence_ids": expected_ids + (list(extras) if select else []),
                "unfound_sources": [], "relevance_note": "The reader requested these sources.",
                "public_source_checks": [],
            }),
        ),
        ConnectionEvaluationEvent(
            kind="release", status="released", release_source="muse_candidate",
            provenance_verdicts=("pass",),
            released_evidence_ids=tuple(expected_ids + (list(extras) if cite else [])),
        ),
    ))
    return grade_connection_scene(
        scene, response(), events, {scene.props[0].prop_id: "memory-runtime"},
    )


@pytest.mark.parametrize("identity", [EARLIER, PIGEON])
@pytest.mark.parametrize("scene_index", [0, 1])
def test_extra_canonical_passages_inside_reader_scope_remain_failed_quality_judgments(plan, identity, scene_index):
    grades = grade_with_extras(plan.scenes[scene_index], {identity: book_record(identity)})

    for grade in grades:
        assert grade.failures == ("authorized_book_citation_mismatch", "authorized_book_selection_mismatch")
        assert grade.first_failure_stage == "serendipity_selection"
        assert grade.stages[2].status == "failed"
        assert grade.stages[-1].reason_code == "authorized_book_citation_mismatch"


@pytest.mark.parametrize("cite,select,code,stage", [
    (False, True, "authorized_book_selection_mismatch", "serendipity_selection"),
    (True, False, "authorized_book_citation_mismatch", "deterministic_release"),
])
def test_citation_and_selection_mismatches_are_graded_independently(plan, cite, select, code, stage):
    grades = grade_with_extras(plan.scenes[1], {PIGEON: book_record()}, cite=cite, select=select)

    assert all(grade.failures == (code,) and grade.first_failure_stage == stage for grade in grades)


@pytest.mark.parametrize("field,value", [
    ("work_id", "pg23"), ("book_version_id", "pg11-unregistered"),
    ("chapter_id", "pg11-v01b38ea4-ch04"), ("chapter", 4), ("chapter", True),
    ("part_id", "appendix"), ("location", "A fabricated location"),
    ("source_sha256", "0" * 64), ("source_lines", [1179, 1220]),
    ("excerpt", "A fabricated quotation."), ("trust_level", "external"),
])
def test_forged_extra_record_metadata_retains_mandatory_failures(plan, field, value):
    record = book_record() | {field: value}
    grades = grade_with_extras(plan.scenes[1], {PIGEON: record})

    assert all(grade.failures == ("unpermitted_citation", "unpermitted_selected_evidence") for grade in grades)


@pytest.mark.parametrize("field", [
    "work_id", "book_version_id", "chapter_id", "chapter", "part_id", "location",
    "source_sha256", "source_lines", "excerpt", "trust_level",
])
def test_missing_extra_record_metadata_retains_mandatory_failures(plan, field):
    record = book_record()
    del record[field]
    grades = grade_with_extras(plan.scenes[1], {PIGEON: record})

    assert all(grade.failures == ("unpermitted_citation", "unpermitted_selected_evidence") for grade in grades)


@pytest.mark.parametrize("kind", ["memory", "web"])
def test_extra_nonbook_sources_cannot_use_the_book_quality_exception(plan, kind):
    record = {"evidence_id": "extra-source", "source_kind": kind, "excerpt": "Unapproved source."}
    grades = grade_with_extras(plan.scenes[1], {"extra-source": record})

    assert all(grade.failures == ("unpermitted_citation", "unpermitted_selected_evidence") for grade in grades)


@pytest.mark.parametrize("extras", [
    {"unknown-source": None},
    {PIGEON: None},
    {"pg11-v01b38ea4-ch05-ln1179-1220": "forged-id"},
    {PIGEON: "canonical", "unknown-source": None},
])
def test_missing_unknown_or_mixed_extra_evidence_cannot_be_demoted(plan, extras):
    records = {}
    for identity, value in extras.items():
        record = None if value is None else book_record() | {"evidence_id": identity}
        records[identity] = record
    grades = grade_with_extras(plan.scenes[1], records)

    assert all(grade.failures == ("unpermitted_citation", "unpermitted_selected_evidence") for grade in grades)


def test_canonical_passage_after_reader_ceiling_keeps_mandatory_failures(plan):
    scene = plan.scenes[1]
    scope = scene.source_setup.book_scopes[0].model_copy(update={"safe_ceiling_chapter": 4})
    scene = replace(scene, source_setup=scene.source_setup.model_copy(update={"book_scopes": (scope,)}))
    grades = grade_with_extras(scene, {PIGEON: book_record()})

    assert all("unpermitted_citation" in grade.failures and "unpermitted_selected_evidence" in grade.failures for grade in grades)


def test_explicitly_forbidden_book_is_not_a_quality_exception_even_if_reading_scope_allows_it(plan):
    scene = plan.scenes[1]
    expectation = scene.proposals[0].connection.model_copy(update={
        "book_retrieval": BookRetrievalExpectation(required_work_ids=("pg23",), forbidden_work_ids=("pg11",)),
    })

    assert not _authorized_book_extras(scene, expectation, {PIGEON}, {PIGEON: book_record()})


def test_personal_reflection_does_not_acquire_a_book_permission_from_an_available_scope(plan):
    scene = replace(plan.scenes[2], source_setup=plan.scenes[1].source_setup)

    assert not _authorized_book_extras(scene, scene.proposals[0].connection, {PIGEON}, {PIGEON: book_record()})


@pytest.mark.parametrize("scope_mutation", ["absent", "empty", "wrong_work", "wrong_version"])
def test_missing_or_different_reader_grant_retains_mandatory_failures(plan, scope_mutation):
    scene = plan.scenes[1]
    setup = scene.source_setup
    if scope_mutation == "absent":
        setup = None
    elif scope_mutation == "empty":
        setup = setup.model_copy(update={"book_scopes": ()})
    else:
        field, value = ("work_id", "pg23") if scope_mutation == "wrong_work" else ("book_version_id", "pg11-unregistered")
        setup = setup.model_copy(update={"book_scopes": (setup.book_scopes[0].model_copy(update={field: value}),)})
    observed = replace(scene, source_setup=setup)

    assert not _authorized_book_extras(observed, scene.proposals[0].connection, {PIGEON}, {PIGEON: book_record()})


def test_no_extra_ids_is_not_positive_authority_evidence(plan):
    scene = plan.scenes[1]
    assert not _authorized_book_extras(scene, scene.proposals[0].connection, set(), {})
