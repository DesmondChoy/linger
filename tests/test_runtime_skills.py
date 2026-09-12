"""Shared runtime-skill resources, lineage, and observable evaluation identity."""

import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest
from pydantic import BaseModel, Field, create_model
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from apps.backend.telemetry import run_agent_traced
from evals.synthetic_journals.transcript import SceneTranscriptRecorder
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.evaluation_transcript import bind_evaluation_transcript_sink
from src.linger.prompts import load_prompt


class SkillInput(BaseModel):
    question: str


class SkillOutput(BaseModel):
    answer: str


def skill() -> RuntimeSkill[SkillInput, SkillOutput]:
    return RuntimeSkill(
        role="Muse",
        name="test-assignment",
        shared_instructions="Shared role policy.",
        instructions="Answer the supplied question.",
        input_type=SkillInput,
        output_type=SkillOutput,
    )


def test_fingerprints_track_effective_policy_schemas_and_permissions() -> None:
    selected = skill()
    digest = selected.fingerprint().digest
    changed_inputs = create_model("SkillInput", question=(str, Field(min_length=5)))
    changed_outputs = create_model("SkillOutput", answer=(str, Field(max_length=20)))
    variants = (
        replace(selected, shared_instructions="Changed shared policy."),
        replace(selected, instructions="Changed task policy."),
        replace(selected, input_type=changed_inputs),
        replace(selected, output_type=changed_outputs),
        replace(selected, tools=("test_tool",)),
        replace(selected, capabilities=("test_capability",)),
        replace(selected, validators=("test_validator",)),
        replace(selected, output_retries=2),
        replace(selected, tool_retries=2),
    )
    assert all(variant.fingerprint().digest != digest for variant in variants)
    assert selected.fingerprint(version="renamed").digest == digest


def test_run_options_cannot_leak_mutations_between_runs() -> None:
    selected = skill()
    first = selected.run_options()
    first["metadata"]["linger_skill"] = "foreign-account-task"
    first["retries"]["output"] = 20
    second = selected.run_options()
    assert second["metadata"] == {"linger_skill": selected.skill_id}
    assert second["retries"]["output"] == 1
    with pytest.raises(FrozenInstanceError):
        selected.name = "different"  # type: ignore[misc]


def test_traced_run_records_skill_and_the_effective_instructions() -> None:
    selected = skill()
    observed = []

    def respond(messages, info):
        observed.append(info.instructions)
        assert not info.function_tools
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, {"answer": "synthetic answer"}
        )])

    agent = Agent(FunctionModel(respond), instructions=selected.shared_instructions)
    recorder = SceneTranscriptRecorder()
    fingerprint = selected.fingerprint()

    async def run():
        with bind_evaluation_transcript_sink(recorder):
            return await run_agent_traced(
                agent,
                SkillInput(question="synthetic question").model_dump_json(),
                span_name="muse.test_assignment",
                role="Muse",
                stage="test_assignment",
                input_contract="SkillInput",
                output_contract="SkillOutput",
                prompt_template_id=fingerprint.template_id,
                prompt_version=fingerprint.version,
                prompt_digest=fingerprint.digest,
                failure_code="test_failed",
                **selected.run_options(),
            )

    result = asyncio.run(run())
    assert result.output == SkillOutput(answer="synthetic answer")
    assert observed == [selected.effective_instructions]
    exchange, = recorder.exchanges
    assert exchange.skill_id == selected.skill_id
    assert exchange.prompt_fingerprint == fingerprint
    assert exchange.message_history == ()


def test_role_registry_retains_every_skill_without_duplicate_agents() -> None:
    from evals.synthetic_journals.replay import (
        RUNTIME_PROMPT_FINGERPRINTS,
        evaluation_agents,
        evaluation_skills,
    )

    agents = evaluation_agents()
    assert len(agents) == len({id(agent) for agent in agents}) == 5
    assert {agent.name for agent in agents} == {
        "Muse", "Librarian", "Sculptor", "Serendipity", "Provenance"
    }
    assignments = evaluation_skills()
    assert {assignment.skill_id for assignment in assignments} == {
        "muse.reflection",
        "librarian.boundary-inference",
        "librarian.evidence-assessment",
        "sculptor.memory-curation",
        "sculptor.memory-surfacing",
        "serendipity.connection-discovery",
        "provenance.emotional-preflight",
        "provenance.candidate-review",
        "provenance.curation-review",
    }
    # Muse has two input-specific fingerprints within its one reflection skill.
    assert len({item.template_id for item in RUNTIME_PROMPT_FINGERPRINTS}) == 10
    assert len({item.digest for item in RUNTIME_PROMPT_FINGERPRINTS}) == 10


def test_all_instruction_resources_load_from_an_unrelated_directory(tmp_path, monkeypatch):
    from evals.synthetic_journals.replay import evaluation_skills

    assignments = evaluation_skills()
    monkeypatch.chdir(tmp_path)
    for assignment in assignments:
        package = f"src.linger.agents.{assignment.role.lower()}"
        assert load_prompt("agents", assignment.role.lower()) == assignment.shared_instructions
        assert load_instructions(
            package, f"skills/{assignment.name}/SKILL.md"
        ) == assignment.instructions


def test_validator_roles_keep_fixed_output_contracts() -> None:
    from src.linger.agents.muse.skills import REFLECTION
    from src.linger.agents.serendipity.skills import CONNECTION_DISCOVERY

    assert "output_type" not in REFLECTION.run_options()
    assert "output_type" not in CONNECTION_DISCOVERY.run_options()
