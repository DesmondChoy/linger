"""Run the existing objective replay once while retaining native diagnostics."""

import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))

import logfire

from apps.backend.config import get_settings
from evals.serendipity import objective_replay
from evals.synthetic_journals.evaluation_link import emit_evaluation_link

CASE = ROOT / "evals/serendipity/objective_cases/cross-source-outside-essay-v1.json"


async def main(args):
    OUTPUT = args.output
    DIAGNOSTICS = args.output.with_suffix(".diagnostics.json")
    if OUTPUT.exists() or DIAGNOSTICS.exists():
        raise FileExistsError("Smoke artifacts already exist; refusing to rerun or overwrite them.")
    settings = get_settings()
    if settings.linger_model != "openai:gpt-5.6-luna" or not settings.linger_web_search_enabled:
        raise ValueError("Smoke requires the approved model and explicitly authorized web search.")
    if settings.exa_api_key is None or not settings.exa_api_key.get_secret_value().strip():
        raise RuntimeError("Configured Exa key is unavailable.")
    recorders = []
    evaluations = []
    recorder_type = objective_replay.SceneTranscriptRecorder
    evaluate = objective_replay.Dataset.evaluate

    def observe_recorder():
        recorder = recorder_type()
        recorders.append(recorder)
        return recorder

    async def observe_evaluation(self, *args, **kwargs):
        result = await evaluate(self, *args, **kwargs)
        emit_evaluation_link(result, dataset_name=objective_replay.OBJECTIVE_ID)
        try:
            url = logfire.url_from_eval(result)
        except Exception:
            url = None
        evaluations.append({
            "trace_id": result.trace_id, "span_id": result.span_id,
            "url": url,
        })
        return result

    diagnostics = {
        "model": settings.linger_model, "web_search_enabled": settings.linger_web_search_enabled,
        "case": str(CASE.relative_to(ROOT)), "case_sha256": hashlib.sha256(CASE.read_bytes()).hexdigest(),
        "started_at": datetime.now(UTC).isoformat(), "status": "running",
    }
    try:
        with patch.object(objective_replay, "SceneTranscriptRecorder", observe_recorder), patch.object(
            objective_replay.Dataset, "evaluate", observe_evaluation,
        ):
            report = await objective_replay.run_replay(CASE)
        OUTPUT.write_text(report.model_dump_json(indent=2) + "\n")
        diagnostics["status"] = "complete"
        print(report.model_dump_json(indent=2), flush=True)
    except Exception as error:
        diagnostics.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        diagnostics["recorders"] = []
        for recorder in recorders:
            observed = {"events": [asdict(event) for event in recorder.connection_events]}
            try:
                observed["exchanges"] = [exchange.model_dump(mode="json") for exchange in recorder.exchanges]
            except RuntimeError as error:
                observed["transcript_error"] = str(error)
            diagnostics["recorders"].append(observed)
        diagnostics["evaluations"] = evaluations
        diagnostics["finished_at"] = datetime.now(UTC).isoformat()
        diagnostics["telemetry_flushed"] = logfire.force_flush()
        DIAGNOSTICS.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
