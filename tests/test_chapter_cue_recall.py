"""Frozen Experiment 3 request plans stay valid for their needs."""

import json
from pathlib import Path

import numpy as np
import pytest

from apps.backend.contracts import BookScope, LibrarianRequest
from apps.backend.hybrid_librarian import HybridLibrarian
from apps.backend.librarian import Librarian
from evals.librarian import chapter_cue_recall
from evals.librarian.chapter_cue_recall import NEEDS, PLANS, revised_corpus
from src.linger.agents.librarian.models import (
    BookRequestPlan,
    LibrarianBookRequestInput,
    book_request_span_errors,
)
from src.linger.agents.sculptor.chapter_cue_models import ChapterCueRevision, ChapterCues
from src.linger.corpus import registry
from src.linger.corpus.pinocchio import BOOK as PINOCCHIO


class _Embedding:
    def passage_embed(self, documents):
        return iter(np.ones((len(documents), 2)))

    def query_embed(self, query):
        return iter((np.ones(2),))


class _Reranker:
    def rerank(self, query, documents):
        return [10.0 if query.casefold() in document.casefold() else -10.0 for document in documents]


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


def _existing_cues() -> dict[int, ChapterCues]:
    return {
        unit.chapter_number: ChapterCues(
            chapter_number=unit.chapter_number, routing_description=unit.routing_description,
            characters=unit.characters, retrieval_cues=unit.retrieval_cues,
        )
        for unit in Librarian().units_for(PINOCCHIO.work_id, PINOCCHIO.book_version_id)
    }


def test_revised_cues_reach_search_without_changing_the_canonical_corpus() -> None:
    catalog = registry.CORPORA[PINOCCHIO.work_id].root / "catalog.json"
    before = catalog.read_bytes()
    cues = _existing_cues()
    cues[1] = cues[1].model_copy(update={"retrieval_cues": ("zanzibarine relic",)})
    librarian = HybridLibrarian(read_chapter_cues=True, embedding_model=_Embedding(), reranker=_Reranker())
    request = LibrarianRequest(query="zanzibarine", book_scopes=[
        BookScope(work_id=PINOCCHIO.work_id, book_version_id=PINOCCHIO.book_version_id, chapter_max=3),
    ])

    with revised_corpus(PINOCCHIO.work_id, cues):
        units = Librarian().units_for(PINOCCHIO.work_id, PINOCCHIO.book_version_id)
        bundle = librarian.retrieve(request)

    assert units[0].retrieval_cues == ("zanzibarine relic",)
    assert units[1].retrieval_cues == cues[2].retrieval_cues
    assert bundle.items and {item.chapter for item in bundle.items} == {1}
    assert all("zanzibarine" not in item.excerpt for item in bundle.items)
    assert catalog.read_bytes() == before


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(chapter_cue_recall, "RUNS", tmp_path)
    monkeypatch.setattr(chapter_cue_recall, "_approver", lambda: "Owner")
    return tmp_path


def _propose(runs, stage: int, chapters=None) -> Path:
    chapters = tuple(_existing_cues().values()) if chapters is None else chapters
    revision = ChapterCueRevision(failure_patterns=("A pattern.",), chapters=chapters)
    proposal = runs / f"stage{stage}-proposal.json"
    proposal.write_text(json.dumps({"revision": revision.model_dump(mode="json")}), encoding="utf-8")
    return proposal


def _record(runs, search: str, reached: set[str]) -> None:
    needs = json.loads(NEEDS.read_text(encoding="utf-8"))["practice"]["needs"]
    (runs / f"{search}-practice.json").write_text(json.dumps({
        "identity": chapter_cue_recall._identity(search),
        "needs": [
            {"id": need["id"], "chapter": need["chapter"], "reached": need["id"] in reached, "pool_chapters": []}
            for need in needs
        ],
    }), encoding="utf-8")


def test_scoring_refuses_a_proposal_changed_after_approval(runs) -> None:
    proposal = _propose(runs, 2)
    chapter_cue_recall.approve(2)

    assert len(chapter_cue_recall.approved_cues(2)) == 36
    proposal.write_text(proposal.read_text(encoding="utf-8").replace("A pattern.", "Edited."), encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after approval"):
        chapter_cue_recall.approved_cues(2)


@pytest.mark.parametrize(("change", "error"), [
    (lambda chapters: chapters[1:] + chapters[1:2], "every chapter exactly once"),
    (lambda chapters: (chapters[0].model_copy(update={"retrieval_cues": ("word " * 61,)}), *chapters[1:]),
     "the budget is 60"),
])
def test_approval_holds_proposals_to_coverage_and_budget(runs, change, error) -> None:
    _propose(runs, 2, change(tuple(_existing_cues().values())))
    with pytest.raises(SystemExit, match=error):
        chapter_cue_recall.approve(2)


def test_next_stage_refuses_feedback_from_other_cues(runs) -> None:
    _record(runs, "stage1", {"n01"})
    proposal = _propose(runs, 2)
    chapter_cue_recall.approve(2)
    _record(runs, "stage2", {"n01", "n02"})
    assert len(chapter_cue_recall.revision_input(3).rounds) == 2

    proposal.write_text(proposal.read_text(encoding="utf-8").replace("A pattern.", "Edited."), encoding="utf-8")
    chapter_cue_recall.approve(2)
    with pytest.raises(SystemExit, match="stage2-practice.json is stale"):
        chapter_cue_recall.revision_input(3)


@pytest.mark.parametrize("stage2", [{"n01"}, {"n02", "n03"}])
def test_stage_three_stops_without_a_net_gain_or_after_a_loss(runs, stage2) -> None:
    _record(runs, "stage1", {"n01"})
    _propose(runs, 2)
    chapter_cue_recall.approve(2)
    _record(runs, "stage2", stage2)
    with pytest.raises(SystemExit, match="Stop rule"):
        chapter_cue_recall._check_stop_rule()


def test_sealed_scores_run_once_and_freeze_every_stage(runs) -> None:
    proposal = _propose(runs, 2)
    chapter_cue_recall.approve(2)
    output = runs / "stage2-sealed.json"
    chapter_cue_recall._lock_stages_for_sealed(output)
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit, match="runs once"):
        chapter_cue_recall._lock_stages_for_sealed(output)
    with pytest.raises(SystemExit, match="stages are frozen"):
        chapter_cue_recall.approve(2)
    proposal.write_text(proposal.read_text(encoding="utf-8").replace("A pattern.", "Edited."), encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after approval"):
        chapter_cue_recall._lock_stages_for_sealed(runs / "stage1-sealed.json")
