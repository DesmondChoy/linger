"""Serendipity's offline self-review and the self-improvement loop around it."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.serendipity import self_improvement as loop
from evals.serendipity.harness import load_serendipity_eval_cases
from evals.serendipity.reliability import (
    CaseReliability,
    ReliabilityReport,
    ReliabilitySummary,
    RunOutcome,
)
from src.linger.agents.serendipity.agent import build_serendipity_agent
from src.linger.agents.serendipity.self_review_models import (
    CaseTrace,
    ObservedRun,
    SelfReviewInput,
    SkillCorrection,
    SkillEdit,
    apply_edits,
    correction_errors,
)
from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY
from src.linger.orchestration.serendipity_self_review import propose_skill_correction

INSTRUCTIONS = "Decline when unsure.\nPropose when two records support a bridge."


def trace(case_id: str, passes: int, repeats: int = 2) -> CaseTrace:
    return CaseTrace(
        case_id=case_id, behavior="select", tier="regression", description="A case.",
        task={"cue": "a cue"}, evidence=({"evidence_id": f"{case_id}-evidence", "excerpt": "text"},),
        expected_searches={}, expected={"status": "proposal"}, passes=passes, repeats=repeats,
        runs=(ObservedRun(passed=passes == repeats, status="decline"),),
    )


TASK = SelfReviewInput(
    skill_name="connection-discovery",
    current_instructions=INSTRUCTIONS,
    cases=(trace("case-a", 0), trace("case-b", 1), trace("case-c", 2)),
)


def correction(**changes) -> SkillCorrection:
    data = {
        "notes": [{"case_id": "case-a", "note": "Declined a supported bridge."},
                  {"case_id": "case-b", "note": "Declined once."}],
        "categories": [{"name": "over-decline", "definition": "Declines despite support.",
                        "case_ids": ["case-a", "case-b"]}],
        "target_category": "over-decline",
        "diagnosis": "'unsure' is read as any doubt.",
        "edits": [{"find": "Decline when\n unsure.", "replace": "Decline when no two records support a bridge.",
                   "reason": "Name the evidence test."}],
        "expected_fixes": ["case-a"],
        "at_risk": ["case-c"],
        "risks": "Restraint cases still lack two records.",
    }
    data.update(changes)
    return SkillCorrection.model_validate(data)


def test_edits_replace_exact_passages_once():
    edits = (SkillEdit(find="unsure", replace="evidence is thin", reason="r"),)
    assert apply_edits(INSTRUCTIONS, edits).startswith("Decline when evidence is thin.")
    wrapped = apply_edits("Decline when\nunsure.", (SkillEdit(find="Decline when unsure.", replace="Decline.", reason="r"),))
    assert wrapped == "Decline."
    with pytest.raises(ValueError, match="2 times"):
        apply_edits("when when", (SkillEdit(find="when", replace="x", reason="r"),))
    with pytest.raises(ValueError, match="overlap"):
        apply_edits(INSTRUCTIONS, (
            SkillEdit(find="Decline when", replace="x", reason="r"),
            SkillEdit(find="when unsure", replace="y", reason="r"),
        ))


def test_valid_correction_has_no_errors():
    assert correction_errors(correction(), TASK) == []


@pytest.mark.parametrize(("changes", "message"), [
    ({"notes": [{"case_id": "case-a", "note": "n"}]}, "missing: ['case-b']"),
    ({"notes": [{"case_id": "case-a", "note": "n"}, {"case_id": "case-b", "note": "n"},
                {"case_id": "case-c", "note": "n"}]}, "passed every run"),
    ({"target_category": "something else"}, "target_category"),
    ({"expected_fixes": ["case-c"]}, "expected_fixes"),
    ({"edits": [{"find": "not in the text", "replace": "x", "reason": "r"}]}, "copied exactly"),
    ({"edits": [{"find": "Decline when unsure.", "replace": "Decline as in case-a.", "reason": "r"}]},
     "not refer to evaluation cases"),
    ({"edits": [{"find": "Decline when unsure.", "replace": "Weigh case-b-evidence.", "reason": "r"}]},
     "case-b-evidence"),
    ({"edits": [{"find": "Decline when unsure.", "replace": "word " * 410, "reason": "r"}]}, "under 400"),
])
def test_contract_errors_are_named_for_repair(changes, message):
    assert any(message in error for error in correction_errors(correction(**changes), TASK))


def test_self_review_runs_on_the_shared_agent_without_tools_and_repairs_in_run():
    seen: list[list[str]] = []
    retries: list[str] = []

    def model(messages, info: AgentInfo):
        seen.append([tool.name for tool in info.function_tools])
        retries.extend(
            str(part.content) for message in messages for part in message.parts
            if isinstance(part, RetryPromptPart)
        )
        bad = len(seen) == 1
        payload = correction(expected_fixes=["case-c"] if bad else ["case-a"]).model_dump(mode="json")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"correction": payload})])

    agent = build_serendipity_agent(FunctionModel(model))
    result = asyncio.run(propose_skill_correction(TASK, agent=agent))

    assert seen == [[], []]
    assert len(retries) == 1 and "expected_fixes" in retries[0]
    assert result.expected_fixes == ("case-a",)


def test_held_back_books_never_reach_the_review():
    practice, held_back = loop.split_cases(load_serendipity_eval_cases())
    assert {case.case_id for case in held_back} == {
        case.case_id for case in load_serendipity_eval_cases()
        if "-keller-" in case.case_id or "-pinocchio-" in case.case_id
    }
    assert len(held_back) == 13 and len(practice) == 33
    review = loop.traces(practice, report(practice, [0] * len(practice), repeats=1))
    text = json.dumps([item.model_dump(mode="json") for item in review]).lower()
    assert "keller" not in text and "pinocchio" not in text


def test_candidate_never_changes_the_production_skill():
    candidate = loop.candidate_skill(CONNECTION_DISCOVERY.instructions + "\nNew rule.")
    assert candidate.instructions.endswith("New rule.")
    assert "New rule." not in CONNECTION_DISCOVERY.instructions
    assert candidate.fingerprint().digest != CONNECTION_DISCOVERY.fingerprint().digest


def report(cases, passes: list[int], repeats: int = 5) -> ReliabilityReport:
    rows = tuple(
        CaseReliability(
            case_id=case.case_id, primary_behavior=case.primary_behavior,
            contrast_group=case.contrast_group, tier=case.tier, repeats=repeats, passes=count,
            pass_at_k=count > 0, pass_pow_k=count == repeats, unstable=0 < count < repeats,
            decision_unstable=False, observed_statuses=("proposal",),
            runs=tuple(
                RunOutcome(hard_pass=index < count, status="proposal" if index < count else "decline")
                for index in range(repeats)
            ),
        )
        for case, count in zip(cases, passes)
    )
    summary = ReliabilitySummary(
        case_count=len(rows), repeats=repeats, total_runs=len(rows) * repeats,
        total_passes=sum(passes), run_pass_rate=0.0, cases_pass_pow_k=0, cases_unstable=0,
        cases_never_passed=0, cases_with_unstable_decision=0, suite_pass_pow_k=False,
    )
    return ReliabilityReport(
        run_id="r", generated_at="2026-10-06T00:00:00Z", model="test", prompt_digests={},
        dataset_digest="d", concurrency=1, summary=summary, tiers={}, cases=rows,
    )


CASES = load_serendipity_eval_cases()[:4]


@pytest.mark.parametrize(("before", "after", "passed", "reason"), [
    ([0, 0, 5, 3], [5, 5, 5, 3], True, "meets"),
    ([0, 0, 5, 3], [5, 4, 5, 3], False, "gain 9"),
    ([0, 0, 5, 3], [5, 5, 5, 0], False, "lost more than 2"),
    ([0, 0, 5, 3], [5, 5, 3, 5], False, "stable cases fell below 4"),
])
def test_decision_follows_the_pre_registered_pass_mark(before, after, passed, reason):
    decision = loop.decide(report(CASES, before), report(CASES, after))
    assert decision.passed is passed
    assert any(reason in item for item in decision.reasons)


def test_loop_pairs_every_comparison_confirms_a_pass_and_reuses_records(tmp_path: Path, monkeypatch):
    practice, held_back = loop.split_cases(load_serendipity_eval_cases())
    single: list[int] = []
    paired: list[tuple[int, tuple[str, ...]]] = []
    reviewed: list[SelfReviewInput] = []

    async def fake_experiment(*, repeats, cases, concurrency, discovery_skill):
        assert discovery_skill is CONNECTION_DISCOVERY
        single.append(len(cases))
        return report(cases, [2] * len(cases))

    async def fake_paired(skills, *, repeats, cases, concurrency):
        assert skills["production"] is CONNECTION_DISCOVERY
        paired.append((len(cases), tuple(skills)))
        return {"production": report(cases, [2] * len(cases)), "candidate": report(cases, [5] * len(cases))}

    async def fake_review(task):
        reviewed.append(task)
        failing = sorted(case.case_id for case in task.cases if case.passes < case.repeats)
        return SkillCorrection(
            notes=tuple({"case_id": case_id, "note": "Declined."} for case_id in failing),
            categories=({"name": "over-decline", "definition": "d", "case_ids": failing},),
            target_category="over-decline", diagnosis="d",
            edits=(SkillEdit(find=task.current_instructions[:40], replace="Changed opening.", reason="r"),),
            expected_fixes=(failing[0],), risks="r",
        )

    monkeypatch.setattr(loop, "run_reliability_experiment", fake_experiment)
    monkeypatch.setattr(loop, "run_paired_reliability", fake_paired)
    monkeypatch.setattr(loop, "propose_skill_correction", fake_review)
    monkeypatch.setattr(loop, "configure_component_evaluation_telemetry", lambda agent: None)

    summary = asyncio.run(loop.run_loop(tmp_path))

    assert single == [33]
    assert paired == [(33, ("production", "candidate"))] * 2 + [(13, ("production", "candidate"))]
    assert summary["rounds"][0]["outcome"] == "confirmed"
    assert summary["held_back"]["baseline"] == 26 and summary["held_back"]["candidate"] == 65
    assert {case.case_id for case in reviewed[0].cases} == {case.case_id for case in practice}
    assert json.loads((tmp_path / "protocol.json").read_text())["design_version"] == 2
    for name in ("round-0/practice.json", "round-1/review-input.json", "round-1/correction.json",
                 "round-1/candidate-SKILL.md", "round-1/practice-production.json",
                 "round-1/practice-candidate.json", "round-1/decision.json",
                 "round-1/confirm-production.json", "round-1/confirm-candidate.json",
                 "round-1/confirm-decision.json", "final/held-back-production.json",
                 "final/held-back-candidate.json", "summary.md"):
        assert (tmp_path / name).exists(), name

    single.clear(); paired.clear(); reviewed.clear()
    asyncio.run(loop.run_loop(tmp_path))
    assert single == [] and paired == [] and reviewed == []


def test_an_unconfirmed_pass_does_not_count(tmp_path: Path, monkeypatch):
    calls = {"pairs": 0}

    async def fake_experiment(*, repeats, cases, concurrency, discovery_skill):
        return report(cases, [2] * len(cases))

    async def fake_paired(skills, *, repeats, cases, concurrency):
        calls["pairs"] += 1
        gain = 5 if calls["pairs"] % 2 == 1 else 2  # passes, then fails to confirm
        return {"production": report(cases, [2] * len(cases)), "candidate": report(cases, [gain] * len(cases))}

    async def fake_review(task):
        failing = sorted(case.case_id for case in task.cases if case.passes < case.repeats)
        return SkillCorrection(
            notes=tuple({"case_id": case_id, "note": "n"} for case_id in failing),
            categories=({"name": "c", "definition": "d", "case_ids": failing},),
            target_category="c", diagnosis="d",
            edits=(SkillEdit(find=task.current_instructions[:40], replace=f"Opening {len(task.earlier_rounds)}.", reason="r"),),
            expected_fixes=(failing[0],), risks="r",
        )

    monkeypatch.setattr(loop, "run_reliability_experiment", fake_experiment)
    monkeypatch.setattr(loop, "run_paired_reliability", fake_paired)
    monkeypatch.setattr(loop, "propose_skill_correction", fake_review)
    monkeypatch.setattr(loop, "configure_component_evaluation_telemetry", lambda agent: None)

    summary = asyncio.run(loop.run_loop(tmp_path, max_rounds=1))
    assert summary["rounds"][0]["outcome"] == "not confirmed"
    assert summary["held_back"] is None and summary["promotion"] == "no candidate confirmed"


def test_rate_limited_runs_wait_and_run_again_instead_of_failing(monkeypatch):
    from pydantic_ai.exceptions import ModelHTTPError

    from evals.serendipity import reliability

    calls: list[int] = []
    sleeps: list[float] = []

    async def flaky_run_case(case, *, agent, discovery_skill):
        calls.append(1)
        if len(calls) == 1:
            raise ModelHTTPError(status_code=429, model_name="test", body={"message": "Rate limit"})
        raise RuntimeError("model output error")

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(reliability, "run_case", flaky_run_case)
    monkeypatch.setattr(reliability.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(reliability, "build_serendipity_agent", lambda: None)
    result = asyncio.run(reliability.run_reliability_experiment(
        repeats=1, cases=load_serendipity_eval_cases()[:1], configure_logfire=False,
    ))

    run = result.cases[0].runs[0]
    assert len(calls) == 2 and sleeps == [reliability.RATE_LIMIT_BACKOFF_SECONDS]
    assert run.status == "execution_error" and "RuntimeError" in run.failures[0]
    assert run.rate_limit_retries == 1


def test_only_a_reasoned_self_review_change_may_amend_a_recorded_protocol(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(loop, "configure_component_evaluation_telemetry", lambda agent: None)

    async def stop(*args, **kwargs):
        raise RuntimeError("stop after the protocol check")

    monkeypatch.setattr(loop, "_score", stop)
    with pytest.raises(RuntimeError):
        asyncio.run(loop.run_loop(tmp_path))
    path = tmp_path / "protocol.json"
    recorded = json.loads(path.read_text())

    path.write_text(json.dumps({**recorded, "self_review_digest": "older"}))
    with pytest.raises(SystemExit, match="--amendment"):
        asyncio.run(loop.run_loop(tmp_path))
    with pytest.raises(RuntimeError):
        asyncio.run(loop.run_loop(tmp_path, amendment="line breaks"))
    amended = json.loads(path.read_text())
    assert amended["amendments"][0]["old"] == "older" and amended["amendments"][0]["reason"] == "line breaks"

    path.write_text(json.dumps({**amended, "pass_mark": {**amended["pass_mark"], "min_practice_gain": 1}}))
    with pytest.raises(SystemExit, match="different protocol"):
        asyncio.run(loop.run_loop(tmp_path, amendment="anything"))


def test_paired_scoring_alternates_skills_within_each_case(monkeypatch):
    from types import SimpleNamespace

    from evals.serendipity import reliability

    seen: list[str] = []
    first = loop.candidate_skill(CONNECTION_DISCOVERY.instructions + "\nFirst.")
    second = loop.candidate_skill(CONNECTION_DISCOVERY.instructions + "\nSecond.")

    async def fake_run_case(case, *, agent, discovery_skill):
        seen.append("a" if discovery_skill is first else "b")
        return SimpleNamespace()

    def fake_outcome(report):
        return RunOutcome(hard_pass=seen[-1] == "a", status="proposal")

    monkeypatch.setattr(reliability, "run_case", fake_run_case)
    monkeypatch.setattr(reliability, "_outcome_from_report", fake_outcome)
    monkeypatch.setattr(reliability, "build_serendipity_agent", lambda: None)
    reports = asyncio.run(reliability.run_paired_reliability(
        {"a": first, "b": second}, repeats=2, cases=load_serendipity_eval_cases()[:1], configure_logfire=False,
    ))

    assert seen == ["a", "b", "a", "b"]
    assert reports["a"].summary.total_passes == 2 and reports["b"].summary.total_passes == 0
    assert reports["a"].prompt_digests != reports["b"].prompt_digests
