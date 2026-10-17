"""Deploy a reviewed release-candidate commit to the existing native Railway service."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_candidate import api, configuration, validate_repository_sha, validate_run


PROJECT = "6db691f2-f510-4018-aaaf-4be0ddef2b8a"
ENVIRONMENT = "8c15d264-a440-439c-a75a-20e454e97745"
SERVICE = "7283294a-c4d8-4908-b7ae-8c5e2fa40913"
SITE = "https://linger-production-b81b.up.railway.app"
TERMINAL_FAILURES = {"FAILED", "CRASHED", "REMOVED", "CANCELED", "CANCELLED", "SKIPPED"}


def validate_promotion(pull: dict, repository: str, sha: str | None = None) -> None:
    for side, branch in (("head", "main"), ("base", "release-candidate")):
        value = pull.get(side, {})
        if (value.get("ref") != branch
                or (value.get("repo") or {}).get("full_name", "").lower() != repository.lower()):
            raise ValueError("Promotion must be a same-repository main to release-candidate PR.")
    if sha is not None and (not pull.get("merged_at") or pull.get("merge_commit_sha") != sha):
        raise ValueError("Candidate must be the resulting commit of a merged promotion PR.")


def resolve(repository: str, sha: str, run_id: str) -> dict:
    validate_repository_sha(repository, sha)
    if not run_id.isdecimal():
        raise ValueError("CI run ID must be numeric.")
    run = api(repository, f"actions/runs/{run_id}")
    validate_run(run, sha, repository)
    policy = configuration(repository, sha)
    if policy["configuration_sha"] != sha:
        raise ValueError("Candidate is stale: only the current release-candidate tip may deploy.")
    if policy["live_evaluations_enabled"] or policy["auto_publish_enabled"]:
        raise ValueError("Native CI-only deployment requires paid evaluations and image publication disabled.")
    promotions = []
    for pull in api(repository, f"commits/{sha}/pulls?per_page=100"):
        try:
            validate_promotion(pull, repository, sha)
        except ValueError:
            continue
        promotions.append(pull)
    if len(promotions) != 1:
        raise ValueError("Candidate requires exactly one merged main to release-candidate promotion PR.")
    return {
        "candidate_sha": sha, "ci_run_id": run_id, "ci_url": run["html_url"],
        "promotion_url": promotions[0]["html_url"],
    }


def command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def deployments() -> list[dict]:
    return json.loads(command(
        "railway", "deployment", "list", "--project", PROJECT, "--environment", ENVIRONMENT,
        "--service", SERVICE, "--limit", "50", "--json",
    ))


def wait_for_deployment(message: str, timeout: float = 1200) -> dict:
    deadline = time.monotonic() + timeout
    deployment_id = None
    while time.monotonic() < deadline:
        matches = [item for item in deployments() if item.get("meta", {}).get("cliMessage") == message]
        if len(matches) > 1:
            raise ValueError("More than one Railway deployment has this run's unique identity.")
        if matches:
            deployment = matches[0]
            if deployment_id is not None and deployment["id"] != deployment_id:
                raise ValueError("Railway deployment identity changed while waiting.")
            deployment_id = deployment["id"]
            status = deployment["status"]
            if status in TERMINAL_FAILURES:
                raise ValueError(f"Railway deployment {deployment_id} ended with {status}.")
            if status == "SUCCESS":
                metadata = deployment.get("meta", {})
                builder = metadata.get("serviceManifest", {}).get("build", {}).get("builder")
                if builder != "RAILPACK":
                    raise ValueError("Railway deployment did not use the native Railpack builder.")
                if "/var/lib/linger" not in metadata.get("volumeMounts", []):
                    raise ValueError("Railway deployment is missing the persistent Linger state volume.")
                return deployment
        time.sleep(10)
    raise TimeoutError(f"Railway deployment {deployment_id or message} did not become healthy in time.")


def verify_site() -> dict:
    # These GET requests do not invoke a provider, create accounts, or write user data.
    with urlopen(f"{SITE}/api/ready", timeout=30) as response:
        if response.status != 200 or json.load(response).get("status") != "ready":
            raise ValueError("The public API is not ready.")
    with urlopen(f"{SITE}/", timeout=30) as response:
        html = response.read().decode()
        if (response.status != 200 or "text/html" not in response.headers.get("Content-Type", "")
                or 'id="root"' not in html):
            raise ValueError("The public frontend did not return the Linger application HTML.")
    return {"ready": True, "frontend": True, "provider_calls": 0}


def deploy(repository: str, sha: str, run_id: str, source: Path, output: Path) -> dict:
    record = {"candidate_sha": sha, "ci_run_id": run_id, "site": SITE, "status": "failed"}
    try:
        source = source.resolve(strict=True)
        if command("git", "rev-parse", "HEAD", cwd=source) != sha:
            raise ValueError("Upload checkout does not match the CI-approved commit.")
        if command("git", "status", "--porcelain", "--untracked-files=normal", cwd=source):
            raise ValueError("Upload checkout must be clean.")
        if not (source / "railpack.json").is_file() or not (source / ".railwayignore").is_file():
            raise ValueError("Upload checkout requires native Railpack configuration and upload exclusions.")
        run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
        if not run.isdecimal() or not attempt.isdecimal():
            raise ValueError("Deployment requires a GitHub run and attempt identity.")
        message = f"GitHub release {sha} run {run} attempt {attempt}"
        record.update(resolve(repository, sha, run_id))
        record["message"] = message
        # Revalidate after the serialized job acquires production, immediately before upload.
        command(
            "railway", "up", "--project", PROJECT, "--environment", ENVIRONMENT,
            "--service", SERVICE, "--detach", "--yes", "--message", message, cwd=source,
        )
        deployment = wait_for_deployment(message)
        record.update({
            "deployment_id": deployment["id"], "railway_status": deployment["status"],
            "builder": "RAILPACK", "image_digest": deployment["meta"].get("imageDigest"),
        })
        record["verification"] = verify_site()
        record["status"] = "success"
        return record
    except Exception as error:
        record["error"] = str(error)
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary).open("a") as stream:
                stream.write("## Native Railway deployment\n\n```json\n")
                stream.write(json.dumps(record, indent=2) + "\n```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    promotion = actions.add_parser("promotion")
    promotion.add_argument("--event", type=Path, required=True)
    promotion.add_argument("--repository", required=True)
    for name in ("resolve", "deploy"):
        child = actions.add_parser(name)
        child.add_argument("--repository", required=True)
        child.add_argument("--sha", required=True)
        child.add_argument("--run-id", required=True)
        if name == "deploy":
            child.add_argument("--source", type=Path, required=True)
            child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "promotion":
        validate_promotion(json.loads(args.event.read_text())["pull_request"], args.repository)
        print("Promotion source verified: main to release-candidate.")
    elif args.action == "resolve":
        print(json.dumps(resolve(args.repository, args.sha, args.run_id), indent=2))
    else:
        print(json.dumps(deploy(args.repository, args.sha, args.run_id, args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
