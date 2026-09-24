"""One-shot adapters for the approved saved release and notebook evaluations."""

import argparse
import ast
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))

import logfire
from opentelemetry.trace import format_trace_id, get_current_span

from apps.backend.config import get_settings
from apps.backend.telemetry import configure_component_evaluation_telemetry, configure_synthetic_evaluation_telemetry
from evals.librarian import live_validation
from evals.librarian.benchmark import Hit, load_cases, measure
from evals.synthetic_journals.replay import evaluation_agents
from src.linger.agents.librarian.agent import librarian_agent
from src.linger.agents.muse.tools import librarian_search
from src.linger.contracts.librarian import RetrievalResult
from src.linger.contracts.reading import ReadingBoundary
from src.linger.contracts.turn import ConfirmedReading
from src.linger.corpus.alice import BOOK, BOOK_VERSION_ID, WORK_ID
from src.linger.orchestration.turn_context import reset_confirmed_reading, set_confirmed_reading, reset_reader_message, set_reader_message


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def notebook_helpers():
    notebook = json.loads((ROOT / "notebooks/librarian_manual_evaluation.ipynb").read_text())
    cell = next(cell for cell in notebook["cells"] if cell["id"] == "response-evaluator")
    namespace = dict(globals(), source_lines=BOOK.default_source.read_text().splitlines())
    exec(compile(ast.parse("".join(cell["source"])), "notebook-response-evaluator", "exec"), namespace)
    return namespace["run_evaluation_case"], namespace["evaluate_librarian_response"]


async def main(args):
    progress_path = args.output.with_suffix(".progress.json")
    if args.output.exists() or progress_path.exists():
        raise FileExistsError("Evaluation output already exists; refusing to overwrite it.")
    settings = get_settings()
    if settings.linger_model != "openai:gpt-5.6-luna" or settings.linger_web_search_enabled:
        raise ValueError("This approved book-only run requires the confirmed model and web search disabled.")
    if args.mode == "release":
        configure_synthetic_evaluation_telemetry(evaluation_agents())
    else:
        configure_component_evaluation_telemetry(librarian_agent)
    progress = {
        "mode": args.mode, "model": settings.linger_model,
        "started_at": datetime.now(UTC).isoformat(), "status": "running", "cases": [],
    }
    write_json(progress_path, progress)
    try:
        with logfire.span("librarian.standalone.{mode}", mode=args.mode):
            progress["trace_id"] = format_trace_id(get_current_span().get_span_context().trace_id)
            if args.mode == "release":
                run_case = live_validation._run_case

                async def record_case(case):
                    progress["active_case"] = case.case_id
                    write_json(progress_path, progress)
                    with logfire.span("librarian.release_case", case_id=case.case_id):
                        result = await run_case(case)
                    progress["cases"].append(result)
                    write_json(progress_path, progress)
                    return result

                live_validation._run_case = record_case
                try:
                    report = await live_validation.run_validation()
                finally:
                    live_validation._run_case = run_case
            else:
                run_case, evaluate = notebook_helpers()
                cases = load_cases().cases
                for index, case in enumerate(cases, 1):
                    print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
                    progress["active_case"] = case.case_id
                    write_json(progress_path, progress)
                    started = perf_counter()
                    with logfire.span("librarian.notebook_case", case_id=case.case_id):
                        response = await run_case(case)
                    row = evaluate(case, response)
                    row["latency_ms"] = round((perf_counter() - started) * 1000, 1)
                    row["response"] = response.model_dump(mode="json")
                    progress["cases"].append(row)
                    write_json(progress_path, progress)
                rows = progress["cases"]
                results = [row for row in rows if row["response_kind"] == "result"]
                summary = {
                    "case_count": len(rows), "result_count": len(results),
                    "strength_accuracy": sum(row["strength_correct"] for row in rows) / len(rows),
                    "mean_evidence_recall": sum(row["evidence_recall"] for row in results) / len(results) if results else None,
                    "mean_final_evidence_precision": sum(row["final_evidence_precision"] for row in results) / len(results) if results else None,
                    "all_spoiler_safe": all(row["spoiler_safe"] for row in results) if results else None,
                    "all_citations_resolve": all(row["citations_resolve"] for row in results) if results else None,
                }
                report = {
                    "model": settings.linger_model, "generated_at": datetime.now(UTC).isoformat(),
                    "notebook": "notebooks/librarian_manual_evaluation.ipynb",
                    "case_set": "evals/librarian/cases.json", "summary": summary, "cases": rows,
                }
        progress["status"] = "complete"
        progress.pop("active_case", None)
        report["trace_id"] = progress["trace_id"]
        write_json(args.output, report)
        print(json.dumps(report["summary"], indent=2), flush=True)
    except Exception as error:
        progress["status"] = "failed"
        progress["error_type"] = type(error).__name__
        raise
    finally:
        progress["finished_at"] = datetime.now(UTC).isoformat()
        progress["telemetry_flushed"] = logfire.force_flush()
        write_json(progress_path, progress)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("release", "direct"))
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
