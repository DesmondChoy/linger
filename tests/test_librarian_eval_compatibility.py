"""Saved Librarian eval entry points bind the current application tool contract."""

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.backend import sessions
from apps.backend.chat_turn import prepare_reflection_turn
from apps.backend.schemas import ChatRequest
from evals.librarian import live_validation
from evals.librarian.benchmark import load_cases
from src.linger.contracts.turn import ConfirmedReading
from src.linger.corpus.alice import BOOK_VERSION_ID, WORK_ID
from src.linger.orchestration import turn_context


@pytest.mark.parametrize("case", load_cases().cases, ids=lambda case: case.case_id)
def test_live_eval_declares_exact_completed_chapter(case):
    session_id = f"eval-compatibility:{case.case_id}"
    try:
        inspection, _, _ = prepare_reflection_turn(
            ChatRequest(session_id=session_id, message=live_validation._chat_message(case)),
            allow_memory_capture=False,
        )
        context = inspection.muse_turn["reading_context"]
        assert context is not None
        assert (context["work_id"], context["chapter_max"], context["boundary_source"]) == (
            WORK_ID, case.chapter_max, "reader_confirmed",
        )
    finally:
        sessions.clear(session_id)


def test_live_eval_binds_reader_message_and_restores_context(monkeypatch):
    case = load_cases().cases[0]
    observed = []

    class StopBeforeProvider(Exception):
        pass

    async def reflection(*args, **kwargs):
        observed.append(turn_context.reader_message())
        raise StopBeforeProvider

    monkeypatch.setattr(live_validation, "prepare_reflection_turn", lambda *a, **k: (
        SimpleNamespace(muse_turn={"reading_context": {"work_id": WORK_ID, "chapter_max": case.chapter_max}}),
        "offline input", {},
    ))
    monkeypatch.setattr(live_validation, "reflection_reply", reflection)
    token = turn_context.set_reader_message("outer reader")
    try:
        with pytest.raises(StopBeforeProvider):
            asyncio.run(live_validation._run_case(case))
        assert observed == [live_validation._chat_message(case)]
        assert turn_context.reader_message() == "outer reader"
    finally:
        turn_context.reset_reader_message(token)


@pytest.mark.parametrize("helper", ["run_librarian", "run_evaluation_case"])
def test_notebook_helpers_bind_reader_message_with_current_search_signature(helper):
    notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/librarian_manual_evaluation.ipynb").read_text())
    definitions = [node for cell in notebook["cells"] if cell["cell_type"] == "code"
                   for node in ast.parse("".join(cell["source"])).body
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == helper]
    case = load_cases().cases[0]
    observed = []

    async def search(work_id, book_version_id, max_final_evidence=5):
        observed.append((turn_context.reader_message(), turn_context.confirmed_reading()))
        assert work_id == WORK_ID and book_version_id == BOOK_VERSION_ID
        return "result"

    namespace = {
        "librarian_search": search,
        "ConfirmedReading": ConfirmedReading, "WORK_ID": WORK_ID, "BOOK_VERSION_ID": BOOK_VERSION_ID,
        **{name: getattr(turn_context, name) for name in (
            "set_confirmed_reading", "reset_confirmed_reading", "set_reader_message", "reset_reader_message",
        )},
    }
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "notebook-helper", "exec"), namespace)
    token = turn_context.set_reader_message("outer reader")
    try:
        call = namespace[helper](case) if helper == "run_evaluation_case" else namespace[helper](case.query, case.chapter_max, "completed")
        assert asyncio.run(call) == "result"
        assert observed[0][0] == case.query
        assert observed[0][1].chapter_max == case.chapter_max
        assert turn_context.reader_message() == "outer reader"
    finally:
        turn_context.reset_reader_message(token)
