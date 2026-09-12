"""Per-run contracts and isolation on Provenance's one reusable Agent."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from src.linger.agents.muse.models import NoMemoryCandidate
from src.linger.agents.provenance.agent import build_provenance_agent
from src.linger.agents.provenance.curation_models import (
    CurationReviewInput,
    CurationSourceEvidence,
)
from src.linger.agents.provenance.models import (
    CandidateUnderReview,
    CurrentLine,
    ProvenanceContext,
    ProvenanceInput,
    ProvenancePolicy,
)
from src.linger.agents.provenance.skills import (
    CANDIDATE_REVIEW,
    CURATION_REVIEW,
    EMOTIONAL_PREFLIGHT,
    PACKAGE,
    SHARED_INSTRUCTIONS,
    SKILLS,
)
from src.linger.agents.sculptor.models import CurationProposal, DuplicateLink
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.contracts.emotional import (
    EmotionalBoundaryAssessment,
    EmotionalBoundaryInput,
    EmotionalContentPolicy,
)


def task_input(skill: RuntimeSkill[Any, Any], marker: str) -> Any:
    if skill is EMOTIONAL_PREFLIGHT:
        return EmotionalBoundaryInput(
            current_line=marker, policy=EmotionalContentPolicy()
        )
    if skill is CANDIDATE_REVIEW:
        return ProvenanceInput(
            context=ProvenanceContext(
                policy=ProvenancePolicy(
                    spoiler_ceiling=None,
                    allow_retrieval=False,
                    allow_connection=False,
                    allow_memory_capture=False,
                ),
                reading_context=None,
            ),
            candidate=CandidateUnderReview(
                response=marker,
                memory=NoMemoryCandidate(
                    kind="no_memory_candidate", reason_code="transient_or_low_signal"
                ),
            ),
            current_line=CurrentLine(text=marker),
        )
    return CurationReviewInput(
        proposal_digest="a" * 64,
        proposal=CurationProposal(
            kind="curation_proposal",
            action=DuplicateLink(
                action="link_duplicates", source_memory_ids=("memory-1", "memory-2")
            ),
        ),
        sources=tuple(
            CurationSourceEvidence(
                memory_id=f"memory-{index}", text=marker, record_sha256=str(index) * 64
            )
            for index in (1, 2)
        ),
    )


def valid_output(skill: RuntimeSkill[Any, Any]) -> dict[str, Any]:
    if skill is EMOTIONAL_PREFLIGHT:
        return {"decision": "continue_reflection"}
    if skill is CANDIDATE_REVIEW:
        return {
            "response_decision": "pass",
            "capture_decision": "no_candidate",
            "emotional_boundary_decision": "not_required",
            "findings": [],
        }
    return {"proposal_digest": "a" * 64, "decision": "allow", "findings": []}


def invalid_output(skill: RuntimeSkill[Any, Any]) -> dict[str, Any]:
    output = valid_output(skill)
    if skill is EMOTIONAL_PREFLIGHT:
        output["rationale"] = "An extra field outside the permitted contract."
    elif skill is CANDIDATE_REVIEW:
        output["response_decision"] = "reject"
    else:
        output["decision"] = "reject"
    return output


def test_concurrent_tasks_select_only_their_instructions_schema_and_input() -> None:
    async def run() -> None:
        entered = asyncio.Event()
        snapshots: list[tuple[RuntimeSkill[Any, Any], str]] = []

        async def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
            assert not info.function_tools
            assert not info.allow_text_output
            assert len(info.output_tools) == 1
            schema = info.output_tools[0].parameters_json_schema
            properties = set(schema["properties"])
            if "response_decision" in properties:
                skill = CANDIDATE_REVIEW
            elif "proposal_digest" in properties:
                skill = CURATION_REVIEW
            else:
                skill = EMOTIONAL_PREFLIGHT
                assert properties == {"decision"}

            # Only the selected policy is present before the first decision.
            assert info.instructions == skill.effective_instructions
            for other in SKILLS:
                if other is not skill:
                    assert other.instructions not in info.instructions

            assert len(messages) == 1
            assert isinstance(messages[0], ModelRequest)
            assert len(messages[0].parts) == 1
            assert isinstance(messages[0].parts[0], UserPromptPart)
            payload = messages[0].parts[0].content
            assert isinstance(payload, str)
            snapshots.append((skill, payload))
            if len(snapshots) == len(SKILLS):
                entered.set()
            await asyncio.wait_for(entered.wait(), timeout=5)
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, valid_output(skill))]
            )

        agent = build_provenance_agent(FunctionModel(respond))
        results = await asyncio.gather(
            *(
                agent.run(
                    task_input(skill, f"private-{skill.name}").model_dump_json(),
                    **skill.run_options(),
                )
                for skill in SKILLS
            )
        )
        for skill, result in zip(SKILLS, results, strict=True):
            assert isinstance(result.output, skill.output_type)
            assert result.metadata == {"linger_skill": skill.skill_id}
        for skill, payload in snapshots:
            assert f"private-{skill.name}" in payload
            for other in SKILLS:
                if other is not skill:
                    assert f"private-{other.name}" not in payload

    asyncio.run(run())


@pytest.mark.parametrize("skill", SKILLS, ids=lambda skill: skill.name)
def test_output_contract_validation_retries_are_task_specific(
    skill: RuntimeSkill[Any, Any],
) -> None:
    calls = 0

    def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls > 1:
            assert any(
                isinstance(part, RetryPromptPart)
                for message in messages
                for part in message.parts
            )
        output = (
            invalid_output(skill)
            if calls <= skill.output_retries
            else valid_output(skill)
        )
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    agent = build_provenance_agent(FunctionModel(respond))
    result = agent.run_sync(
        task_input(skill, "reader data").model_dump_json(), **skill.run_options()
    )
    assert isinstance(result.output, skill.output_type)
    assert calls == skill.output_retries + 1


@pytest.mark.parametrize("skill", SKILLS, ids=lambda skill: skill.name)
def test_invalid_output_cannot_exceed_the_selected_retry_limit(
    skill: RuntimeSkill[Any, Any],
) -> None:
    calls = 0

    def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, invalid_output(skill))]
        )

    agent = build_provenance_agent(FunctionModel(respond))
    with pytest.raises(UnexpectedModelBehavior, match="output retries"):
        agent.run_sync(
            task_input(skill, "reader data").model_dump_json(), **skill.run_options()
        )
    assert calls == skill.output_retries + 1


def test_concurrent_model_overrides_are_local_to_the_run_context() -> None:
    async def run() -> None:
        base_model = TestModel(custom_output_args={"decision": "continue_reflection"})
        agent = build_provenance_agent(base_model)
        entered = asyncio.Event()
        count = 0

        async def run_override(decision: str, marker: str) -> EmotionalBoundaryAssessment:
            async def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
                nonlocal count
                count += 1
                if count == 2:
                    entered.set()
                await asyncio.wait_for(entered.wait(), timeout=5)
                payload = json.loads(messages[0].parts[0].content)
                assert payload["current_line"] == marker
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, {"decision": decision})]
                )

            with agent.override(model=FunctionModel(respond)):
                result = await agent.run(
                    task_input(EMOTIONAL_PREFLIGHT, marker).model_dump_json(),
                    **EMOTIONAL_PREFLIGHT.run_options(),
                )
                return result.output

        results = await asyncio.gather(
            run_override("apply_boundary", "account-one-data"),
            run_override("continue_reflection", "account-two-data"),
        )
        assert [result.decision for result in results] == [
            "apply_boundary", "continue_reflection"
        ]
        final = await agent.run(
            task_input(EMOTIONAL_PREFLIGHT, "base-model-data").model_dump_json(),
            **EMOTIONAL_PREFLIGHT.run_options(),
        )
        assert final.output.decision == "continue_reflection"
        assert base_model.last_model_request_parameters is not None

    asyncio.run(run())


def test_evaluation_entry_points_select_skills_under_one_production_override() -> None:
    from evals.provenance.emotional_boundary import classify_with_configured_agent
    from evals.provenance.risk_codes import (
        load_risk_code_cases,
        review_with_configured_agent,
    )
    from src.linger.agents.provenance.agent import provenance_agent

    seen = []

    async def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        properties = info.output_tools[0].parameters_json_schema["properties"]
        skill = (
            CANDIDATE_REVIEW
            if "response_decision" in properties
            else EMOTIONAL_PREFLIGHT
        )
        assert info.instructions == skill.effective_instructions
        assert not info.function_tools
        seen.append(skill.skill_id)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, valid_output(skill))]
        )

    async def run() -> None:
        case = next(
            case
            for case in load_risk_code_cases().cases
            if case.expected_response_decision == "pass"
            and case.expected_capture_decision == "no_candidate"
        )
        with provenance_agent.override(model=FunctionModel(respond)):
            preflight, review = await asyncio.gather(
                classify_with_configured_agent("An ordinary reading reflection."),
                review_with_configured_agent(case),
            )
        assert preflight.decision == "continue_reflection"
        assert review.response_decision == "pass"
        assert set(seen) == {EMOTIONAL_PREFLIGHT.skill_id, CANDIDATE_REVIEW.skill_id}

    asyncio.run(run())


def test_resources_and_fingerprints_do_not_depend_on_working_directory(
    tmp_path: Any, monkeypatch: Any,
) -> None:
    fingerprints = {skill.name: skill.fingerprint() for skill in SKILLS}
    monkeypatch.chdir(tmp_path)
    assert load_instructions(PACKAGE, "shared.md") == SHARED_INSTRUCTIONS
    for skill in SKILLS:
        assert (
            load_instructions(PACKAGE, f"skills/{skill.name}/SKILL.md")
            == skill.instructions
        )
        assert skill.fingerprint() == fingerprints[skill.name]
        assert (
            replace(skill, shared_instructions="changed policy").fingerprint()
            != skill.fingerprint()
        )
        assert replace(skill, output_type=str).fingerprint() != skill.fingerprint()
