"""Bind release evidence to successful release-candidate CI and the images that CI tested."""

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
from evals.release.policy import parse_threshold, publication_decision


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
            raise ValueError("Candidate artifacts must come from this repository, never a fork.")


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
                stream.write("Live evaluations are disabled. Evaluation and publication jobs are skipped.\n")
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
    artifacts = api(repository, f"actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
    for arch in ("amd64", "arm64"):
        name = f"linger-candidate-{sha}-{arch}"
        matches = [artifact for artifact in artifacts if artifact["name"] == name and not artifact["expired"]]
        if len(matches) != 1:
            raise ValueError(f"Exactly one retained {arch} candidate is required. Re-run CI if artifacts expired.")
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
        if (run.get("status") not in {"passed", "review_required"}
                or run.get("execution_status") != "completed" or run.get("returncode") != 0
                or run.get("problems") != [] or results.get("blocking_failures") != []
                or results.get("execution_failures") != []
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


def publication_authorization(
    summary: dict, *, sha: str, image_id: str, route: str,
    live_enabled: str, auto_enabled: str, threshold: str, configuration_sha: str, approvals: list,
) -> dict:
    if live_enabled != "true":
        raise ValueError("Live evaluation is disabled; publication is forbidden.")
    if not re.fullmatch(r"[0-9a-f]{40}", configuration_sha):
        raise ValueError("Publication requires an exact configuration commit identity.")
    if route not in {"manual", "automatic"} or summary.get("status") not in {"passed", "review_required"}:
        raise ValueError("Complete release evidence is required before publication.")
    identity = summary.get("identity", {})
    if identity.get("candidate_sha") != sha or identity.get("image_id") != image_id:
        raise ValueError("Publication evidence does not match the evaluated candidate image.")
    decision = summary.get("publication", {})
    if decision.get("route") != route or type(decision.get("auto_publish_enabled")) is not bool:
        raise ValueError("Publication route differs from the recorded evaluation policy.")
    if auto_enabled not in {"true", "false"} or decision["auto_publish_enabled"] != (auto_enabled == "true"):
        raise ValueError("Automatic publication setting differs from the recorded policy.")
    passed, total = validate_publication_evidence(summary)
    expected = publication_decision(
        judgments_passed=passed, judgments_total=total, complete=True, blocked=False,
        auto_publish_enabled=auto_enabled == "true", threshold=threshold,
    )
    if decision != expected:
        raise ValueError("Publication policy differs from the decision computed from complete evidence.")
    if route == "automatic" and auto_enabled != "true":
        raise ValueError("Automatic publication is disabled.")
    if route == "manual" and not any(
        approval.get("state") == "approved"
        and any(environment.get("name") == "linger-release" for environment in approval.get("environments", []))
        for approval in approvals
    ):
        raise ValueError("Manual publication requires recorded linger-release approval.")
    return {
        "candidate_sha": sha, "image_id": image_id, "live_evaluations_enabled": True,
        "configuration_sha": configuration_sha, "publication": decision, "human_approvals": approvals,
    }


def archive_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_image(info: dict, sha: str, arch: str, image_id: str) -> None:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Candidate image ID must be a sha256 digest.")
    if info.get("Id") != image_id or info.get("Architecture") != arch or info.get("Os") != "linux":
        raise ValueError("Loaded image identity or architecture differs from the tested candidate.")
    if info.get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != sha:
        raise ValueError("Image revision label differs from the selected candidate SHA.")


def create_manifest(sha: str, arch: str, image: str, directory: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Candidate SHA must be a full Git commit identity.")
    info = json.loads(command("docker", "image", "inspect", image))[0]
    validate_image(info, sha, arch, info["Id"])
    manifest = {
        "schema_version": 1, "candidate_sha": sha, "architecture": arch,
        "image_id": info["Id"], "archive_sha256": archive_hash(directory / "image.tar.gz"),
    }
    (directory / "candidate.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_candidate(sha: str, arch: str, directory: Path) -> dict:
    manifest = json.loads((directory / "candidate.json").read_text())
    if (manifest.get("schema_version"), manifest.get("candidate_sha"), manifest.get("architecture")) != (1, sha, arch):
        raise ValueError("Artifact does not describe the requested candidate.")
    archive = directory / "image.tar.gz"
    if archive_hash(archive) != manifest.get("archive_sha256"):
        raise ValueError("Candidate archive checksum changed.")
    image_id = manifest.get("image_id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Artifact image ID is not a digest.")
    command("docker", "load", "--input", str(archive))
    info = json.loads(command("docker", "image", "inspect", image_id))[0]
    validate_image(info, sha, arch, image_id)
    return manifest


def emit(value: dict) -> None:
    print(json.dumps(value, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            for key in ("candidate_sha", "ci_run_id", "image_id", "configuration_sha", "live_evaluations_enabled", "auto_publish_enabled", "auto_publish_threshold"):
                if key in value:
                    rendered = str(value[key]).lower() if type(value[key]) is bool else str(value[key])
                    stream.write(f"{key}={rendered}\n")


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
    for action in ("create", "verify"):
        child = commands.add_parser(action)
        child.add_argument("--arch", choices=["amd64", "arm64"], required=True)
        child.add_argument("--directory", type=Path, required=True)
        if action == "create":
            child.add_argument("--image", required=True)
    for child in commands.choices.values():
        child.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        if args.action == "resolve":
            result = resolve(args.repository, args.sha, args.run_id)
        elif args.action == "configuration":
            result = configuration(args.repository, args.sha)
        elif args.action == "authorize":
            result = publication_authorization(
                json.loads(args.summary.read_text()), sha=args.sha, image_id=args.image_id,
                route=args.route, live_enabled=args.live_enabled, auto_enabled=args.auto_enabled,
                threshold=args.threshold, configuration_sha=args.configuration_sha,
                approvals=json.loads(args.approvals.read_text()) if args.approvals else [],
            )
            result["evaluation_summary_sha256"] = archive_hash(args.summary)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        elif args.action == "create":
            result = create_manifest(args.sha, args.arch, args.image, args.directory)
        else:
            result = verify_candidate(args.sha, args.arch, args.directory)
        emit(result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Candidate validation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
