"""Deploy a published, approved image to Railway; retries never build or evaluate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_candidate import api, configuration, publication_authorization, validate_repository_sha, validate_run

PROJECT = "6db691f2-f510-4018-aaaf-4be0ddef2b8a"
ENVIRONMENT = "8c15d264-a440-439c-a75a-20e454e97745"
SERVICE = "7283294a-c4d8-4908-b7ae-8c5e2fa40913"
VOLUME = "da3aff80-4c28-42c3-8317-5eb51fc85c7c"
SITE = "https://linger-production-b81b.up.railway.app"
TERMINAL_FAILURES = {"FAILED", "CRASHED", "REMOVED", "CANCELED", "CANCELLED", "SKIPPED"}
DIGEST = r"sha256:[0-9a-f]{64}"


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
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("CI run ID must be positive and numeric.")
    run = api(repository, f"actions/runs/{run_id}")
    validate_run(run, sha, repository)
    policy = configuration(repository, sha)
    if policy["configuration_sha"] != sha:
        raise ValueError("Candidate is stale: only the current release-candidate tip may deploy.")
    promotions = []
    for pull in api(repository, f"commits/{sha}/pulls?per_page=100"):
        try:
            validate_promotion(pull, repository, sha)
        except ValueError:
            continue
        promotions.append(pull)
    if len(promotions) != 1:
        raise ValueError("Candidate requires exactly one merged main to release-candidate promotion PR.")
    return {"candidate_sha": sha, "ci_run_id": run_id, "ci_url": run["html_url"],
            "promotion_url": promotions[0]["html_url"], "policy": policy}


def diagnostic(text: str) -> str:
    secrets = {os.environ[name] for name in ("RAILWAY_TOKEN", "RAILWAY_API_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
               if os.environ.get(name)}
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)\bBearer\s+[^\s\"',;]+", "Bearer [REDACTED]", text)
    return text[:4000] + "\n[truncated]" if len(text) > 4000 else text


def command(*args: str) -> str:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        details = [f"{Path(args[0]).name} failed (exit code {error.returncode})."]
        for label, output in (("stdout", error.stdout), ("stderr", error.stderr)):
            if output and output.strip():
                details.append(f"{label}:\n{diagnostic(output.strip())}")
        # The original exception includes command arguments that may contain credentials.
        raise RuntimeError("\n".join(details)) from None


def approved(approvals: list) -> bool:
    return any(item.get("state") == "approved" and any(
        environment.get("name") == "linger-release" for environment in item.get("environments", [])
    ) for item in approvals)


def validate_publication(record: dict, repository: str, run_id: str, attempt: str, evidence: Path) -> dict:
    sha = record.get("candidate_sha", "")
    validate_repository_sha(repository, sha)
    if record.get("github_run_id") != run_id or record.get("github_run_attempt") != attempt:
        raise ValueError("Publication record belongs to another run or attempt.")
    reference = record.get("release_image", "")
    if not re.fullmatch(rf"ghcr\.io/{re.escape(repository.lower())}@{DIGEST}", reference):
        raise ValueError("Deployment requires this repository's immutable GHCR image digest.")
    image, authorization = record.get("image", {}), record.get("authorization", {})
    image_id = image.get("image_id", "")
    if (not re.fullmatch(DIGEST, image_id) or image.get("platform") != "linux/amd64"
            or image.get("candidate_sha") != sha or authorization.get("candidate_sha") != sha
            or authorization.get("image_id") != image_id or authorization.get("configuration_sha") != sha):
        raise ValueError("Publication does not bind the approved image, platform, and candidate.")
    ci_run_id = record.get("ci_run_id", "")
    resolved = resolve(repository, sha, ci_run_id)
    policy = resolved["policy"]
    if (json.loads((evidence / "image.json").read_text()) != image
            or json.loads((evidence / "publication.json").read_text()) != authorization):
        raise ValueError("Publication record differs from its retained image or authorization evidence.")
    route = authorization.get("publication", {}).get("route")
    summary_bytes = (evidence / "behavioral/summary.json").read_bytes()
    expected = publication_authorization(
        json.loads(summary_bytes), sha=sha, image_id=image_id, route=route,
        live_enabled=str(policy["live_evaluations_enabled"]).lower(),
        auto_enabled=str(policy["auto_publish_enabled"]).lower(),
        threshold=str(policy["auto_publish_threshold"]), configuration_sha=sha,
        approvals=json.loads((evidence / "approvals.json").read_text()) if route == "manual" else [],
        configuration=json.loads((evidence / "release-configuration.json").read_text()),
        image_checks=json.loads((evidence / "image-checks.json").read_text()),
    )
    summary_hash = "evaluation_summary_sha256" if policy["live_evaluations_enabled"] else "skipped_evaluation_record_sha256"
    expected[summary_hash] = hashlib.sha256(summary_bytes).hexdigest()
    if authorization != expected:
        raise ValueError("Publication authorization differs from the retained release evidence and current policy.")
    if route == "manual":
        if not approved(api(repository, f"actions/runs/{run_id}/approvals")):
            raise ValueError("Publication requires recorded human release approval.")
    return resolved


def load_publication(repository: str, run_id: str, attempt: str, destination: Path) -> dict:
    if any(not value.isdecimal() or int(value) < 1 for value in (run_id, attempt)):
        raise ValueError("Select positive numeric publication run and attempt IDs.")
    run = api(repository, f"actions/runs/{run_id}/attempts/{attempt}")
    if (run.get("path", "").split("@")[0] != ".github/workflows/release-auto.yml"
            or run.get("event") != "workflow_run" or run.get("head_branch") != "main"
            or any(run.get(key, {}).get("full_name", "").lower() != repository.lower()
                   for key in ("repository", "head_repository"))):
        raise ValueError("Select an automatic release run from this repository's protected main branch.")
    jobs = api(repository, f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")["jobs"]
    publications = [job for job in jobs if re.fullmatch(r"Publish approved [0-9a-f]{40}", job.get("name", "").split(" / ")[-1])]
    if len(publications) != 1 or publications[0].get("conclusion") != "success":
        raise ValueError("The selected attempt has no successful image publication job.")
    artifacts = api(repository, f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    pattern = rf"release-publication-[0-9a-f]{{40}}-{run_id}-{attempt}"
    matches = [item for item in artifacts if re.fullmatch(pattern, item.get("name", "")) and not item.get("expired")]
    if len(matches) != 1:
        raise ValueError("Publication evidence is missing, expired, or ambiguous; do not rebuild for a retry.")
    command("gh", "run", "download", run_id, "--repo", repository,
            "--name", matches[0]["name"], "--dir", str(destination))
    record = json.loads((destination / "approved-release.json").read_text())
    validate_publication(record, repository, run_id, attempt, destination)
    expected = f"release-publication-{record['candidate_sha']}-{run_id}-{attempt}"
    if (matches[0]["name"] != expected
            or publications[0]["name"].split(" / ")[-1] != f"Publish approved {record['candidate_sha']}"):
        raise ValueError("Publication artifact, successful job, and recorded candidate differ.")
    return record


def public_image(reference: str, image_id: str) -> dict:
    """Read manifests anonymously; never forward GitHub or Railway credentials."""
    namespace, digest = reference.removeprefix("ghcr.io/").split("@")
    query = urlencode({"service": "ghcr.io", "scope": f"repository:{namespace}:pull"})
    try:
        with urlopen(f"https://ghcr.io/token?{query}", timeout=30) as response:
            token = json.load(response)["token"]
        headers = {"Authorization": f"Bearer {token}", "Accept": ", ".join((
            "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
        ))}

        def manifest(identity: str) -> dict:
            with urlopen(Request(f"https://ghcr.io/v2/{namespace}/manifests/{identity}", headers=headers), timeout=30) as response:
                body = response.read(1024 * 1024)
            if f"sha256:{hashlib.sha256(body).hexdigest()}" != identity:
                raise ValueError("Public registry manifest differs from the approved digest.")
            return json.loads(body)

        value = manifest(digest)
        if "manifests" in value:
            platforms = [item for item in value["manifests"] if item.get("platform", {}).get("os") == "linux"
                         and item.get("platform", {}).get("architecture") == "amd64"]
            if len(platforms) != 1 or not re.fullmatch(DIGEST, platforms[0].get("digest", "")):
                raise ValueError("Published image must identify one Linux AMD64 manifest.")
            value = manifest(platforms[0]["digest"])
        if value.get("config", {}).get("digest") != image_id:
            raise ValueError("Published manifest does not contain the tested image.")
    except Exception as error:
        raise ValueError("Cannot verify public access to the approved image. Make the GHCR package public, then retry deployment only.") from error
    return {"public": True, "manifest_digest": digest, "image_id": image_id}


def railway_api(query: str, variables: dict) -> dict:
    response = json.loads(command("railway", "api", query, "--variables", json.dumps(variables), "--compact"))
    if response.get("errors") or response.get("data") is None:
        detail = diagnostic(json.dumps(response.get("errors") or response))
        raise ValueError(f"Railway API did not confirm the operation: {detail}")
    return response["data"]


def service() -> dict:
    return railway_api("""query($service:String!,$environment:String!){
      serviceInstance(serviceId:$service,environmentId:$environment){
        source{image repo} healthcheckPath activeDeployments{id status}
      }}""", {"service": SERVICE, "environment": ENVIRONMENT})["serviceInstance"]


def preflight() -> None:
    value = railway_api("""query($project:String!,$environment:String!){
      project(id:$project){environments{edges{node{id}}}}
      environment(id:$environment){projectId volumeInstances{edges{node{
        serviceId volumeId mountPath isPendingDeletion
      }}}}}""", {"project": PROJECT, "environment": ENVIRONMENT})
    if {edge["node"]["id"] for edge in value["project"]["environments"]["edges"]} != {ENVIRONMENT}:
        raise ValueError("Review environment isolation before updating a project with multiple environments.")
    environment = value["environment"]
    if environment["projectId"] != PROJECT or not any(
        item["node"]["serviceId"] == SERVICE and item["node"]["volumeId"] == VOLUME
        and item["node"]["mountPath"] == "/var/lib/linger" and not item["node"]["isPendingDeletion"]
        for item in environment["volumeInstances"]["edges"]
    ):
        raise ValueError("Existing production service and persistent volume must be preserved.")
    if service()["healthcheckPath"] != "/api/ready":
        raise ValueError("Production readiness healthcheck must remain enabled.")


def wait_for_deployment(deployment_id: str, reference: str, timeout: float = 1200) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        deployment = railway_api("query($id:String!){deployment(id:$id){id projectId environmentId serviceId status meta}}", {"id": deployment_id})["deployment"]
        if (deployment["id"] != deployment_id or deployment["projectId"] != PROJECT
                or deployment["environmentId"] != ENVIRONMENT or deployment["serviceId"] != SERVICE):
            raise ValueError("Railway deployment belongs to another project, service, or environment.")
        status = deployment["status"]
        if status in TERMINAL_FAILURES:
            raise ValueError(f"Railway deployment {deployment_id} ended with {status}.")
        if status == "SUCCESS":
            metadata = deployment.get("meta") or {}
            if metadata.get("imageDigest") != reference.split("@")[1]:
                raise ValueError("Railway did not report the exact published image digest.")
            if "/var/lib/linger" not in metadata.get("volumeMounts", []):
                raise ValueError("Railway deployment is missing the persistent state mount.")
            current = service()
            if ((current.get("source") or {}).get("image") != reference
                    or not any(item["id"] == deployment_id and item["status"] == "SUCCESS"
                               for item in current["activeDeployments"])):
                raise ValueError("The exact approved deployment is not active on the existing service.")
            return deployment
        time.sleep(10)
    raise TimeoutError(f"Railway deployment {deployment_id} did not become healthy in time.")


def verify_site() -> dict:
    with urlopen(f"{SITE}/api/ready", timeout=30) as response:
        if response.status != 200 or json.load(response).get("status") != "ready":
            raise ValueError("The public API is not ready.")
    with urlopen(f"{SITE}/", timeout=30) as response:
        if (response.status != 200 or "text/html" not in response.headers.get("Content-Type", "")
                or 'id="root"' not in response.read().decode()):
            raise ValueError("The public frontend did not return the Linger application HTML.")
    return {"ready": True, "frontend": True, "provider_calls": 0}


def deploy(repository: str, run_id: str, attempt: str, output: Path) -> dict:
    record = {"publication_run_id": run_id, "publication_attempt": attempt, "site": SITE, "status": "failed"}
    try:
        with tempfile.TemporaryDirectory(prefix="railway-publication-") as directory:
            publication = load_publication(repository, run_id, attempt, Path(directory))
            reference, sha = publication["release_image"], publication["candidate_sha"]
            record.update({"candidate_sha": sha, "release_image": reference, "ci_run_id": publication["ci_run_id"],
                           "evaluation_status": publication["authorization"]["evaluation_status"]})
            record["registry"] = public_image(reference, publication["image"]["image_id"])
            preflight()
            # Recheck the release tip and policy after waiting for concurrency and registry/API reads.
            validate_publication(publication, repository, run_id, attempt, Path(directory))
        # The image entrypoint repairs volume ownership, then drops to UID/GID 10001.
        # Saving this variable must not start a deployment of the previous source.
        initialized = railway_api("mutation($input:VariableUpsertInput!){variableUpsert(input:$input)}", {
            "input": {"projectId": PROJECT, "environmentId": ENVIRONMENT, "serviceId": SERVICE,
                      "name": "RAILWAY_RUN_UID", "value": "0", "skipDeploys": True},
        })
        if not initialized["variableUpsert"]:
            raise ValueError("Railway did not confirm the state-volume initialization setting.")
        updated = railway_api("""mutation($service:String!,$environment:String!,$input:ServiceInstanceUpdateInput!){
          serviceInstanceUpdate(serviceId:$service,environmentId:$environment,input:$input)
        }""", {"service": SERVICE, "environment": ENVIRONMENT,
                 "input": {"source": {"image": reference, "repo": None}}})
        if not updated["serviceInstanceUpdate"] or (service().get("source") or {}).get("image") != reference:
            raise ValueError("Railway did not save the approved image source.")
        result = railway_api("""mutation($service:String!,$environment:String!){
          serviceInstanceDeployV2(serviceId:$service,environmentId:$environment)
        }""", {"service": SERVICE, "environment": ENVIRONMENT})
        record["deployment_id"] = result["serviceInstanceDeployV2"]
        wait_for_deployment(record["deployment_id"], reference)
        record["railway_status"] = "SUCCESS"
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
                stream.write("## Approved Railway image deployment\n\n```json\n")
                stream.write(json.dumps(record, indent=2) + "\n```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    promotion = actions.add_parser("promotion")
    promotion.add_argument("--event", type=Path, required=True)
    promotion.add_argument("--repository", required=True)
    deployment = actions.add_parser("deploy")
    deployment.add_argument("--repository", required=True)
    deployment.add_argument("--publication-run-id", required=True)
    deployment.add_argument("--publication-attempt", required=True)
    deployment.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "promotion":
        validate_promotion(json.loads(args.event.read_text())["pull_request"], args.repository)
        print("Promotion source verified: main to release-candidate.")
    else:
        print(json.dumps(deploy(args.repository, args.publication_run_id, args.publication_attempt, args.output), indent=2))


if __name__ == "__main__":
    main()
