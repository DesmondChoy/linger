from export_catalog import scene_record


def test_keeps_nested_book_grade_failures_without_inventing_an_overall_verdict():
    record = scene_record({
        "scene_id": "pigeon-reflection",
        "grades": [
            {"hard_pass": False, "failures": ["retrieval_used_unpermitted_evidence"]},
            {"hard_pass": True, "failures": []},
        ],
    })
    assert record == {
        "id": "pigeon-reflection",
        "result": "Recorded grade failure",
        "failures": ["retrieval_used_unpermitted_evidence"],
    }


def test_absence_of_failures_does_not_become_a_pass():
    record = scene_record({"scene_id": "example", "grades": [{"hard_pass": True}]})
    assert record["result"] == "No overall verdict in this summary"


def test_preserves_recorded_verdict_and_deduplicates_failure_codes():
    record = scene_record({
        "scene_id": "example",
        "ground_truth_result": "fails_hard_gates",
        "gate_failures": ["missing_retrieval"],
        "grades": [{"failures": ["missing_retrieval", "wrong_source"]}],
    })
    assert record["result"] == "fails_hard_gates"
    assert record["failures"] == ["missing_retrieval", "wrong_source"]
