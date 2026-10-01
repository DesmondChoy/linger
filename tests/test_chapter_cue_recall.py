"""Frozen Experiment 3 request plans stay valid for their needs."""

import json

from evals.librarian.chapter_cue_recall import NEEDS, PLANS
from src.linger.agents.librarian.models import (
    BookRequestPlan,
    LibrarianBookRequestInput,
    book_request_span_errors,
)


def test_every_need_has_a_valid_frozen_plan() -> None:
    needs = json.loads(NEEDS.read_text(encoding="utf-8"))
    plans = json.loads(PLANS.read_text(encoding="utf-8"))["plans"]
    questions = {
        need["id"]: need["question"]
        for set_name in ("practice", "sealed")
        for need in needs[set_name]["needs"]
    }

    assert set(plans) == set(questions)
    for need_id, question in questions.items():
        plan = BookRequestPlan.model_validate(plans[need_id])
        assert book_request_span_errors(plan, LibrarianBookRequestInput(current_line=question)) == [], need_id
