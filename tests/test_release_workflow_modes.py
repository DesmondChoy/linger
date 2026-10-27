"""Exercise release routing and credential contracts across workflow calls."""

import ast
from pathlib import Path
import re

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release-checks.yml"
EVALUATION_SECRETS = {
    "RELEASE_EVAL_OPENAI_API_KEY", "RELEASE_EVAL_ANTHROPIC_API_KEY",
    "RELEASE_EVAL_GOOGLE_API_KEY", "RELEASE_EVAL_EXA_API_KEY", "RELEASE_EVAL_LOGFIRE_TOKEN",
}


def workflow(name):
    # BaseLoader preserves GitHub's `on` key instead of treating it as a YAML 1.1 boolean.
    return yaml.load(WORKFLOW.with_name(name).read_text(), Loader=yaml.BaseLoader)


def referenced_secrets(value):
    return set(re.findall(r"\bsecrets\.([A-Za-z_][A-Za-z_0-9]*)", yaml.safe_dump(value)))


@pytest.mark.parametrize("caller_name", ["release-auto.yml", "release.yml"])
def test_release_callers_forward_only_the_declared_evaluation_secrets(caller_name):
    caller = workflow(caller_name)["jobs"]["release"]
    assert caller["uses"] == "./.github/workflows/release-checks.yml"
    assert caller.get("secrets") == {
        name: "${{ secrets." + name + " }}" for name in EVALUATION_SECRETS
    }
    called = workflow("release-checks.yml")
    assert set(called["on"]["workflow_call"]["secrets"]) == EVALUATION_SECRETS
    assert referenced_secrets(called["jobs"]["evaluate"]) == EVALUATION_SECRETS


def test_evaluation_secret_values_are_optional_until_live_preflight():
    declarations = workflow("release-checks.yml")["on"]["workflow_call"]["secrets"]
    assert set(declarations) == EVALUATION_SECRETS
    # Disabled evaluations and unused model providers must not require credentials.
    assert all(secret["required"] == "false" for secret in declarations.values())


def test_evaluation_credentials_stay_in_the_protected_evaluation_job():
    called = workflow("release-checks.yml")
    assert called["jobs"]["evaluate"]["environment"] == "linger-evaluations"
    assert not referenced_secrets(called.get("env", {}))
    for name, job in called["jobs"].items():
        if name != "evaluate":
            assert not referenced_secrets(job) & EVALUATION_SECRETS


def test_railway_call_forwards_only_its_required_deployment_token():
    caller = workflow("release-auto.yml")["jobs"]["railway"]
    assert caller["uses"] == "./.github/workflows/railway-deploy.yml"
    assert caller.get("secrets") == {"RAILWAY_TOKEN": "${{ secrets.RAILWAY_TOKEN }}"}
    called = workflow("railway-deploy.yml")
    declarations = called["on"]["workflow_call"]["secrets"]
    assert set(declarations) == {"RAILWAY_TOKEN"}
    assert declarations["RAILWAY_TOKEN"]["required"] == "true"
    assert "workflow_dispatch" in called["on"]
    assert called["jobs"]["deploy"]["environment"]["name"] == "railway-production"
    assert referenced_secrets(called["jobs"]["deploy"]) == {"RAILWAY_TOKEN"}


def expression(source, needs, *, cancelled=False, success=True):
    """Evaluate only the boolean/string expression subset used by these jobs."""
    source = source.removeprefix("${{").removesuffix("}}").strip()
    source = re.sub(r"!(?!=)", " not ", source.replace("&&", " and ").replace("||", " or "))
    tree = ast.parse(" ".join(source.split()), mode="eval")
    values = {"needs": needs, "true": True, "false": False}
    statuses = {"cancelled": cancelled, "success": success, "always": True}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in {str, bool}:
            return node.value
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.Attribute):
            parent = visit(node.value)
            return parent.get(node.attr, "") if isinstance(parent, dict) else ""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.args and not node.keywords:
            return statuses[node.func.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.BoolOp):
            result = visit(node.values[0])
            for value in node.values[1:]:
                if bool(result) != isinstance(node.op, ast.And):
                    break
                result = visit(value)
            return result
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            left, right = visit(node.left), visit(node.comparators[0])
            return left.casefold() == right.casefold() if isinstance(left, str) and isinstance(right, str) else left == right
        raise AssertionError(f"Unsupported workflow expression: {ast.dump(node)}")

    return visit(tree.body)


def runs(job, needs, *, cancelled=False):
    dependencies = job.get("needs", [])
    dependencies = [dependencies] if isinstance(dependencies, str) else dependencies
    success = not cancelled and all(needs.get(name, {}).get("result") == "success" for name in dependencies)
    condition = job.get("if", "true")
    if not re.search(r"\b(?:always|success|failure|cancelled)\s*\(", condition) and not success:
        return False
    return bool(expression(condition, needs, cancelled=cancelled, success=success))


@pytest.fixture
def jobs():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def results(*, live="false", automatic="false", evaluation="skipped", route=""):
    return {
        "configuration": {"result": "success", "outputs": {"live_enabled": live, "auto_enabled": automatic}},
        "candidate": {"result": "success"},
        "build": {"result": "success"},
        "evaluate": {"result": evaluation, "outputs": {"publication_route": route}},
    }


@pytest.mark.parametrize("live", ["false", "true"])
def test_candidate_and_image_checks_run_in_both_modes(jobs, live):
    needs = results(live=live)
    assert runs(jobs["candidate"], needs)
    assert runs(jobs["build"], needs)
    assert runs(jobs["evaluate"], needs) == (live == "true")


@pytest.mark.parametrize("job,dependency", [
    ("candidate", "configuration"), ("build", "configuration"), ("build", "candidate"),
    ("evaluate", "configuration"), ("evaluate", "candidate"), ("evaluate", "build"),
])
@pytest.mark.parametrize("status", ["failure", "cancelled", "skipped", ""])
def test_required_jobs_never_run_after_an_unsuccessful_dependency(jobs, job, dependency, status):
    needs = results(live="true")
    needs[dependency]["result"] = status
    assert not runs(jobs[job], needs)


@pytest.mark.parametrize("live,automatic,evaluation,reported_route,route,environment", [
    ("false", "false", "skipped", "", "manual", "linger-release"),
    ("false", "true", "skipped", "automatic", "manual", "linger-release"),
    ("true", "false", "success", "manual", "manual", "linger-release"),
    ("true", "true", "success", "manual", "manual", "linger-release"),
    ("true", "true", "success", "automatic", "automatic", "linger-release-auto"),
])
def test_eligible_candidates_select_the_matching_route_and_environment(
    jobs, live, automatic, evaluation, reported_route, route, environment,
):
    needs = results(live=live, automatic=automatic, evaluation=evaluation, route=reported_route)
    publish = jobs["publish"]
    assert runs(publish, needs)
    assert expression(publish["env"]["PUBLICATION_ROUTE"], needs) == route
    assert expression(publish["environment"]["name"], needs) == environment


@pytest.mark.parametrize("live,evaluation", [("false", "skipped"), ("true", "success")])
@pytest.mark.parametrize("dependency", ["configuration", "candidate", "build"])
@pytest.mark.parametrize("status", ["failure", "cancelled", "skipped", ""])
def test_publication_requires_successful_configuration_candidate_and_build(
    jobs, live, evaluation, dependency, status,
):
    needs = results(live=live, evaluation=evaluation, route="manual")
    needs[dependency]["result"] = status
    assert not runs(jobs["publish"], needs)


@pytest.mark.parametrize("evaluation", ["success", "failure", "cancelled", ""])
def test_disabled_mode_requires_an_intentionally_skipped_evaluation(jobs, evaluation):
    needs = results(evaluation=evaluation, automatic="true", route="automatic")
    assert not runs(jobs["publish"], needs)


@pytest.mark.parametrize("evaluation", ["skipped", "failure", "cancelled", ""])
@pytest.mark.parametrize("route", ["manual", "automatic", ""])
def test_enabled_mode_never_falls_back_after_incomplete_or_failed_evaluation(jobs, evaluation, route):
    needs = results(live="true", automatic="true", evaluation=evaluation, route=route)
    assert not runs(jobs["publish"], needs)


@pytest.mark.parametrize("live", ["", "unknown", "0"])
def test_missing_or_unrecognized_live_setting_never_authorizes_publication(jobs, live):
    assert not runs(jobs["publish"], results(live=live))


@pytest.mark.parametrize("route", ["", "blocked", "unknown", "automatic"])
def test_enabled_mode_rejects_missing_blocked_or_unauthorized_routes(jobs, route):
    needs = results(live="true", evaluation="success", route=route)
    assert not runs(jobs["publish"], needs)


@pytest.mark.parametrize("live,evaluation", [("false", "skipped"), ("true", "success")])
def test_cancelled_release_never_publishes(jobs, live, evaluation):
    needs = results(live=live, evaluation=evaluation, route="manual")
    assert not runs(jobs["publish"], needs, cancelled=True)
