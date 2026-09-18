"""Verify the diagnostic adapter offline; these mocks do not judge semantics."""

import asyncio
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
import pytest

BASE = Path(__file__).resolve().parent
ROOT = next(p for p in BASE.parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / "tests"))
from provenance_fixtures import review_with_audits
from evals.provenance import claim_mapping
from src.linger.agents.provenance.agent import provenance_agent
from src.linger.agents.provenance.models import ProvenanceReview, RiskFinding, TextSpanLocation

spec = importlib.util.spec_from_file_location("live_adapter", BASE / "run_live.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_mapping_adapter_records_one_attempt_per_case_without_expected_answers(tmp_path, monkeypatch):
    cases = claim_mapping.load_cases().cases
    received = []

    def respond(messages, info):
        case = cases[len(received)]
        prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
        assert len(prompts) == 1
        payload = json.loads(prompts[0])
        assert payload == case.review_input.model_dump(mode="json")
        received.append(case.case_id)
        findings = () if case.expected_response_decision == "pass" else (RiskFinding(
            code="unsupported_claim", applies_to="response",
            location=TextSpanLocation(kind="text_span", source_field="candidate.response",
                                      path="", quote=case.review_input.candidate.response),
            explanation="Offline adapter fixture; this is not a semantic judgment.",
        ),)
        review = review_with_audits(case.review_input, ProvenanceReview(
            response_decision=case.expected_response_decision, emotional_boundary_decision="not_required",
            capture_decision="no_candidate", findings=findings,
        ))
        review = review.model_copy(update={"claim_audit": tuple(
            audit.model_copy(update={"supported": case.expected_response_decision == "pass"})
            for audit in review.claim_audit
        )})
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, review.model_dump(mode="json"))],
            usage=RequestUsage(input_tokens=100, output_tokens=50, cost=Decimal("0.00001234")),
        )

    monkeypatch.setattr(adapter, "get_settings", lambda: SimpleNamespace(
        linger_model="openai:gpt-5.6-luna", linger_web_search_enabled=False,
    ))
    monkeypatch.setattr(adapter, "configure_component_evaluation_telemetry", lambda agent: None)
    monkeypatch.setattr(adapter.logfire, "force_flush", lambda: True)
    output = tmp_path / "mapping.json"
    args = SimpleNamespace(mode="mapping", output=output)
    with provenance_agent.override(model=FunctionModel(respond)):
        asyncio.run(adapter.main(args))
    report = json.loads(output.read_text())
    assert received == [case.case_id for case in cases]
    assert report["summary"]["targets_pass"] is True
    assert len(report["diagnostics"]) == len(cases)
    assert all(row["model_messages"] and row["review"] for row in report["diagnostics"])
    assert all(row["usage"]["cost"] == "0.00001234" for row in report["diagnostics"])
    assert all("expected_response_decision" not in row["review_input"] for row in report["diagnostics"])
    assert json.loads(output.with_suffix(".progress.json").read_text())["status"] == "complete"
    with pytest.raises(FileExistsError):
        asyncio.run(adapter.main(args))


@pytest.mark.parametrize("failure", ["invalid_output", "http", "unknown"])
def test_mapping_gate_errors_keep_real_attempts_and_sanitized_diagnostics(tmp_path, monkeypatch, failure):
    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        if failure == "http":
            raise ModelHTTPError(503, "PRIVATE_MODEL", "PRIVATE_PROVIDER_BODY")
        if failure == "unknown":
            raise RuntimeError("PRIVATE_EXCEPTION_MESSAGE")
        return ModelResponse(
            parts=[ThinkingPart("PRIVATE_THINKING"), ToolCallPart(info.output_tools[0].name, {})],
            usage=RequestUsage(input_tokens=100, output_tokens=50, cost=Decimal("0.00001234")),
        )

    monkeypatch.setattr(adapter, "get_settings", lambda: SimpleNamespace(
        linger_model="openai:gpt-5.6-luna", linger_web_search_enabled=False,
    ))
    monkeypatch.setattr(adapter, "configure_component_evaluation_telemetry", lambda agent: None)
    monkeypatch.setattr(adapter.logfire, "force_flush", lambda: True)
    output = tmp_path / "failed-mapping.json"
    with provenance_agent.override(model=FunctionModel(respond)):
        asyncio.run(adapter.main(SimpleNamespace(mode="mapping", output=output)))
    report = json.loads(output.read_text())
    assert report["summary"]["cases_passed"] == 0
    assert len(report["diagnostics"]) == 4
    assert calls == (12 if failure == "invalid_output" else 4)
    for row in report["diagnostics"]:
        assert row["status"] == "failure"
        assert row["usage_complete"] is False
        assert row["model_messages"]
        assert row["failure_category"] == {
            "invalid_output": "model_response_error", "http": "provider_error", "unknown": "unknown_error",
        }[failure]
        assert row["provider_status_code"] == (503 if failure == "http" else None)
        assert row["provider_error_kind"] == ("http" if failure == "http" else None)
        if failure == "invalid_output":
            assert sum(m["kind"] == "response" for m in row["model_messages"]) == 3
            assert "retry-prompt" in json.dumps(row["model_messages"])
            assert row["usage"]["requests"] == 3
            assert row["usage"]["input_tokens"] == 300
        else:
            assert not any(m["kind"] == "response" for m in row["model_messages"])
        assert "PRIVATE_" not in json.dumps(row)
    assert json.loads(output.with_suffix(".progress.json").read_text())["cases"] == report["diagnostics"]
