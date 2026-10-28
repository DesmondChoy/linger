"""Validate release candidates, evaluated images, and publication evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evals.release.policy import (
    parse_threshold, publication_decision, skipped_publication_decision, validate_execution_classification,
)


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def api(repository: str, path: str):
    return json.loads(command("gh", "api", "--method", "GET", f"repos/{repository}/{path}"))


def validate_run(run: dict, sha: str, repository: str) -> None:
    expected = {
        "head_sha": sha, "head_branch": "release-candidate", "event": "push",
        "status": "completed", "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError("Candidate requires successful, completed push CI on release-candidate at the requested SHA.")
    if run.get("path", "").split("@")[0] != ".github/workflows/ci.yml":
        raise ValueError("The candidate run is not the CI workflow.")
    for key in ("repository", "head_repository"):
        if run.get(key, {}).get("full_name", "").lower() != repository.lower():
            raise ValueError("Candidate CI must run in this repository, never a fork.")


def validate_environment(environment: dict) -> None:
    if not any(rule.get("type") == "required_reviewers" and rule.get("reviewers")
               for rule in environment.get("protection_rules", [])):
        raise ValueError("Configure required reviewers on the linger-release environment before releasing.")


def validate_repository_sha(repository: str, sha: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name.")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Select a full lowercase 40-character commit SHA.")


def validate_configuration(value: dict) -> dict:
    expected = {"live_evaluations_enabled", "auto_publish_enabled", "auto_publish_threshold"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Release configuration must contain exactly the two switches and threshold.")
    if any(type(value[key]) is not bool for key in ("live_evaluations_enabled", "auto_publish_enabled")):
        raise ValueError("Release switches must be JSON booleans.")
    if type(value["auto_publish_threshold"]) not in {int, float}:
        raise ValueError("Release threshold must be a number between 0 and 100.")
    parse_threshold(value["auto_publish_threshold"])
    return value


def validate_configuration_snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or "configuration_sha" not in value:
        raise ValueError("Release configuration snapshot requires its exact commit identity.")
    sha = value["configuration_sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Release configuration snapshot requires an exact configuration commit identity.")
    validate_configuration({key: setting for key, setting in value.items() if key != "configuration_sha"})
    return value


def configuration(repository: str, sha: str) -> dict:
    validate_repository_sha(repository, sha)
    configuration_sha = api(repository, "branches/release-candidate")["commit"]["sha"]
    validate_repository_sha(repository, configuration_sha)
    response = api(repository, f"contents/.github/release-config.json?ref={configuration_sha}")
    if response.get("type") != "file" or response.get("encoding") != "base64":
        raise ValueError("The release-candidate branch must contain a readable release configuration file.")
    value = validate_configuration(json.loads(base64.b64decode(response["content"]).decode()))
    value["configuration_sha"] = configuration_sha
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write(f"## Release configuration from `{configuration_sha}` for candidate `{sha}`\n\n")
            stream.write("```json\n" + json.dumps(value, indent=2) + "\n```\n\n")
            if not value["live_evaluations_enabled"]:
                stream.write("Live evaluations are intentionally disabled. Image checks and manual publication approval remain required.\n")
    return value


def resolve(repository: str, sha: str, run_id: str) -> dict:
    validate_repository_sha(repository, sha)
    if run_id:
        if not run_id.isdecimal():
            raise ValueError("CI run ID must be numeric.")
        run = api(repository, f"actions/runs/{run_id}")
    else:
        runs = api(repository, f"actions/workflows/ci.yml/runs?head_sha={sha}&branch=release-candidate&event=push&status=success&per_page=100")
        if not runs["workflow_runs"]:
            raise ValueError("No successful release-candidate CI exists for this commit.")
        run = runs["workflow_runs"][0]
    validate_run(run, sha, repository)
    comparison = api(repository, f"compare/{sha}...release-candidate")
    if comparison.get("status") not in {"ahead", "identical"}:
        raise ValueError("Candidate commit is no longer reachable on release-candidate.")
    validate_environment(api(repository, "environments/linger-release"))
    return {"candidate_sha": sha, "ci_run_id": str(run["id"]), "ci_url": run["html_url"]}


def validate_publication_evidence(summary: dict) -> tuple[int, int]:
    totals, runs = summary.get("totals", {}), summary.get("runs", [])
    requested = totals.get("requested_runs")
    if (type(requested) is not int or requested < 1 or not isinstance(runs, list)
            or len(runs) != requested or totals.get("completed_runs") != requested
            or any(totals.get(key) != 0 for key in ("not_started_runs", "failed_runs", "blocked_runs"))
            or summary.get("problems") != []):
        raise ValueError("Complete release evidence is required before publication.")
    counts = {key: 0 for key in ("judgments_passed", "judgments_failed", "judgments_total", "scenes_ungraded")}
    for run in runs:
        results, telemetry = run.get("results", {}), run.get("telemetry", {})
        validate_execution_classification(results)
        if (run.get("status") not in {"passed", "review_required"}
                or run.get("execution_status") != "completed" or run.get("returncode") != 0
                or run.get("problems") != [] or results.get("blocking_failures") != []
                or results.get("blocking_execution_failures") != []
                or telemetry.get("flushed") is not True or not telemetry.get("url")):
            raise ValueError("Publication evidence contains incomplete or blocked execution.")
        if (any(type(results.get(key)) is not int or results[key] < 0 for key in counts)
                or results["judgments_total"] < 1
                or results["judgments_passed"] + results["judgments_failed"] != results["judgments_total"]):
            raise ValueError("Publication evidence has inconsistent judgment counts.")
        for key in counts:
            counts[key] += results[key]
    if any(type(totals.get(key)) is not int or totals[key] != value for key, value in counts.items()):
        raise ValueError("Publication totals differ from the completed evaluation runs.")
    return counts["judgments_passed"], counts["judgments_total"]


def validate_candidate_identity(sha: str, image_id: str) -> None:
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Candidate SHA must be a full Git commit identity.")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Candidate image ID must be a sha256 digest.")


def validate_fallback_artifacts(summary: dict, directory: Path) -> None:
    """Bind the gate's fallback proofs to the retained evidence before publishing."""
    for run in summary.get("runs", []):
        proofs = run.get("results", {}).get("safe_fallbacks", [])
        if not proofs:
            continue
        recorded_path = run.get("artifact")
        if not isinstance(recorded_path, str):
            raise ValueError("Safe fallback has no retained artifact identity.")
        parts = Path(recorded_path).parts[-3:]
        if (len(parts) != 3 or not re.fullmatch(r"repeat-[1-9][0-9]*", parts[0])
                or not re.fullmatch(r"scenario-[1-9][0-9]*", parts[1]) or parts[2] != "evaluation.json"):
            raise ValueError("Safe fallback artifact has an invalid release-relative path.")
        path = directory.joinpath(*parts).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Safe fallback artifact is outside the retained evidence directory.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != run.get("artifact_sha256"):
            raise ValueError("Safe fallback artifact differs from the release gate evidence.")
        artifact = json.loads(raw)
        scenes = artifact.get("scenes") if isinstance(artifact, dict) else None
        if not isinstance(scenes, list) or any(not isinstance(scene, dict) for scene in scenes):
            raise ValueError("Safe fallback artifact has malformed Scene evidence.")
        for proof in proofs:
            matches = [scene for scene in scenes if scene.get("scene_id") == proof["scene_id"]]
            if len(matches) != 1:
                raise ValueError("Safe fallback Scene is missing or duplicated in the retained artifact.")
            encoded = json.dumps(matches[0], sort_keys=True, separators=(",", ":")).encode()
            if hashlib.sha256(encoded).hexdigest() != proof["scene_sha256"]:
                raise ValueError("Safe fallback Scene differs from its verified evidence.")


def validate_image_checks(checks: dict, sha: str, image_id: str) -> dict:
    validate_candidate_identity(sha, image_id)
    expected = {
        "candidate_sha": sha, "image_id": image_id,
        "offline_smoke": "passed", "image_security": "passed",
    }
    if checks != expected:
        raise ValueError("Successful offline smoke and image security checks must match the candidate image.")
    return checks


def record_image_checks(sha: str, image_id: str, offline_status: str, security_status: str) -> dict:
    if offline_status != "success" or security_status != "success":
        raise ValueError("Both image check steps must have a successful outcome.")
    return validate_image_checks({
        "candidate_sha": sha, "image_id": image_id,
        "offline_smoke": "passed", "image_security": "passed",
    }, sha, image_id)


def skipped_evaluations(sha: str, image_id: str, configuration: dict, image_checks: dict) -> dict:
    snapshot = validate_configuration_snapshot(configuration)
    if snapshot["live_evaluations_enabled"] is not False:
        raise ValueError("Only an explicit live-evaluation opt-out can produce skipped evidence.")
    validate_image_checks(image_checks, sha, image_id)
    settings = {key: value for key, value in snapshot.items() if key != "configuration_sha"}
    return {
        "schema_version": 1, "status": "skipped",
        "reason": "Live evaluations were intentionally disabled by release configuration.",
        "identity": {"candidate_sha": sha, "image_id": image_id},
        "configuration_sha": snapshot["configuration_sha"], "settings": settings,
        "publication": skipped_publication_decision(
            auto_publish_enabled=snapshot["auto_publish_enabled"], threshold=snapshot["auto_publish_threshold"],
        ),
    }


def publication_authorization(
    summary: dict, *, sha: str, image_id: str, route: str,
    live_enabled: str, auto_enabled: str, threshold: str, configuration_sha: str, approvals: list,
    configuration: dict, image_checks: dict,
) -> dict:
    snapshot = validate_configuration_snapshot(configuration)
    if live_enabled not in {"true", "false"} or auto_enabled not in {"true", "false"}:
        raise ValueError("Publication switches must be explicit true or false values.")
    if (
        snapshot["configuration_sha"] != configuration_sha
        or snapshot["live_evaluations_enabled"] != (live_enabled == "true")
        or snapshot["auto_publish_enabled"] != (auto_enabled == "true")
        or parse_threshold(snapshot["auto_publish_threshold"]) != parse_threshold(threshold)
    ):
        raise ValueError("Publication settings differ from the recorded configuration snapshot.")
    validate_image_checks(image_checks, sha, image_id)
    if not isinstance(summary, dict) or route not in {"manual", "automatic"}:
        raise ValueError("Complete release evidence is required before publication.")
    identity = summary.get("identity", {})
    if identity.get("candidate_sha") != sha or identity.get("image_id") != image_id:
        raise ValueError("Publication evidence does not match the evaluated candidate image.")
    decision = summary.get("publication", {})
    if decision.get("route") != route or type(decision.get("auto_publish_enabled")) is not bool:
        raise ValueError("Publication route differs from the recorded evaluation policy.")
    if decision["auto_publish_enabled"] != (auto_enabled == "true"):
        raise ValueError("Automatic publication setting differs from the recorded policy.")
    if live_enabled == "true":
        if summary.get("status") not in {"passed", "review_required"}:
            raise ValueError("Complete release evidence is required before publication.")
        passed, total = validate_publication_evidence(summary)
        expected = publication_decision(
            judgments_passed=passed, judgments_total=total, complete=True, blocked=False,
            auto_publish_enabled=snapshot["auto_publish_enabled"], threshold=snapshot["auto_publish_threshold"],
        )
        evaluation_status = "completed"
    else:
        skipped = skipped_evaluations(sha, image_id, snapshot, image_checks)
        if json.dumps(summary, sort_keys=True) != json.dumps(skipped, sort_keys=True):
            raise ValueError("Disabled live evaluation requires the exact unscored skipped-evaluation record.")
        expected = skipped["publication"]
        evaluation_status = "skipped"
    if decision != expected:
        raise ValueError("Publication policy differs from the decision computed from complete evidence.")
    if route == "automatic" and auto_enabled != "true":
        raise ValueError("Automatic publication is disabled.")
    if not isinstance(approvals, list):
        raise ValueError("Publication approvals must be a list of recorded environment reviews.")
    if route == "manual" and not any(
        isinstance(approval, dict) and approval.get("state") == "approved"
        and isinstance(approval.get("environments"), list)
        and any(isinstance(environment, dict) and environment.get("name") == "linger-release"
                for environment in approval["environments"])
        for approval in approvals
    ):
        raise ValueError("Manual publication requires recorded linger-release approval.")
    return {
        "candidate_sha": sha, "image_id": image_id, "live_evaluations_enabled": snapshot["live_evaluations_enabled"],
        "configuration_sha": configuration_sha, "publication": decision, "human_approvals": approvals,
        "evaluation_status": evaluation_status, "image_checks": image_checks,
    }


def validate_image(info: dict, sha: str, image_id: str) -> None:
    validate_candidate_identity(sha, image_id)
    if info.get("Id") != image_id or info.get("Architecture") != "amd64" or info.get("Os") != "linux":
        raise ValueError("Loaded image identity or platform differs from the evaluated Linux AMD64 candidate.")
    if info.get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != sha:
        raise ValueError("Image revision label differs from the selected candidate SHA.")


def inspect_image(sha: str, image_id: str) -> dict:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Candidate image ID must be a sha256 digest.")
    info = json.loads(command("docker", "image", "inspect", image_id))[0]
    validate_image(info, sha, image_id)
    return {"candidate_sha": sha, "image_id": image_id, "platform": "linux/amd64"}


def emit(value: dict) -> None:
    print(json.dumps(value, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            for key in ("candidate_sha", "ci_run_id", "image_id", "configuration_sha", "live_evaluations_enabled", "auto_publish_enabled", "auto_publish_threshold"):
                if key in value:
                    rendered = str(value[key]).lower() if type(value[key]) is bool else str(value[key])
                    stream.write(f"{key}={rendered}\n")
            if "publication" in value:
                stream.write(f"publication_route={value['publication']['route']}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("--repository", required=True)
    resolve_parser.add_argument("--run-id", default="")
    settings_parser = commands.add_parser("configuration")
    settings_parser.add_argument("--repository", required=True)
    authorize_parser = commands.add_parser("authorize")
    authorize_parser.add_argument("--summary", type=Path, required=True)
    authorize_parser.add_argument("--approvals", type=Path)
    authorize_parser.add_argument("--output", type=Path, required=True)
    authorize_parser.add_argument("--image-id", required=True)
    authorize_parser.add_argument("--route", choices=["manual", "automatic"], required=True)
    authorize_parser.add_argument("--live-enabled", required=True)
    authorize_parser.add_argument("--auto-enabled", required=True)
    authorize_parser.add_argument("--threshold", required=True)
    authorize_parser.add_argument("--configuration-sha", required=True)
    authorize_parser.add_argument("--configuration", type=Path, required=True)
    authorize_parser.add_argument("--image-checks", type=Path, required=True)
    checks_parser = commands.add_parser("image-checks")
    checks_parser.add_argument("--image-id", required=True)
    checks_parser.add_argument("--offline-status", required=True)
    checks_parser.add_argument("--security-status", required=True)
    skipped_parser = commands.add_parser("skip-evaluations")
    skipped_parser.add_argument("--image-id", required=True)
    skipped_parser.add_argument("--configuration", type=Path, required=True)
    skipped_parser.add_argument("--image-checks", type=Path, required=True)
    skipped_parser.add_argument("--output", type=Path, required=True)
    image_parser = commands.add_parser("image")
    image_parser.add_argument("--image-id", required=True)
    for child in commands.choices.values():
        child.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        if args.action == "resolve":
            result = resolve(args.repository, args.sha, args.run_id)
        elif args.action == "configuration":
            result = configuration(args.repository, args.sha)
        elif args.action == "authorize":
            summary = json.loads(args.summary.read_text())
            result = publication_authorization(
                summary, sha=args.sha, image_id=args.image_id,
                route=args.route, live_enabled=args.live_enabled, auto_enabled=args.auto_enabled,
                threshold=args.threshold, configuration_sha=args.configuration_sha,
                approvals=json.loads(args.approvals.read_text()) if args.approvals else [],
                configuration=json.loads(args.configuration.read_text()),
                image_checks=json.loads(args.image_checks.read_text()),
            )
            if args.live_enabled == "true":
                validate_fallback_artifacts(summary, args.summary.parent)
            with args.summary.open("rb") as stream:
                field = "evaluation_summary_sha256" if args.live_enabled == "true" else "skipped_evaluation_record_sha256"
                result[field] = hashlib.file_digest(stream, "sha256").hexdigest()
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        elif args.action == "image-checks":
            result = record_image_checks(args.sha, args.image_id, args.offline_status, args.security_status)
        elif args.action == "skip-evaluations":
            result = skipped_evaluations(
                args.sha, args.image_id, json.loads(args.configuration.read_text()),
                json.loads(args.image_checks.read_text()),
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as stream:
                stream.write(json.dumps(result, indent=2) + "\n")
            report = (
                "# Release evaluation intentionally skipped\n\n"
                f"Candidate: `{args.sha}`\n\nImage: `{args.image_id}`\n\n"
                f"Configuration: `{result['configuration_sha']}`\n\n"
                "Live evaluations were intentionally disabled. No evaluation score was produced.\n\n"
                "Offline smoke and image security checks passed. Manual linger-release approval is required for publication.\n"
            )
            args.output.with_name("report.md").write_text(report)
        else:
            result = inspect_image(args.sha, args.image_id)
        emit(result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Candidate validation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
