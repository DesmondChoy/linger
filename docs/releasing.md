# Release a Linger version

Use this guide to promote changes from `main` to `release-candidate`, approve an image, and deploy that image to Railway. The same saved image passes release checks, publication, and deployment. The later sections also cover running an approved image locally.

Paid evaluations and automatic publication are disabled in [`.github/release-config.json`](../.github/release-config.json). With both switches off, the release workflow builds, scans, and smoke-tests an image without provider calls, then waits for human publication approval. After publication, Railway deploys the recorded public GHCR digest. Keep the switches off until the team is ready to run paid evaluations.

The [release checks reference](release-checks.md) describes the checks, publication rules, evidence, and limits. Both security datasets have human-approved Ground truth. Their live runs are intentionally deferred while live evaluations are off.

## Configure GitHub once

These steps need a repository administrator. Repository files cannot configure branch protection, environment reviewers, secrets, or package permissions.

Follow the [Railway setup](railway.md#configure-github-once): protect both branches with PR reviews and the seven CI checks listed in the [reference](release-checks.md#ci-checks), require **Release promotion** on `release-candidate`, configure human reviewers on `linger-release`, and retain the production environment secret. Keep both switches `false`. Railway uses the published image source; keep direct GitHub auto-deploys and image auto-updates disabled.

The publication job needs GitHub Packages write permission through its own `GITHUB_TOKEN`. The first GHCR package must be made public in its package settings before Railway Hobby can pull it. See [public image setup and deployment retries](railway.md#make-the-ghcr-package-public).

The following setup is needed before enabling paid evaluations:

1. Create the `linger-release` environment. Add at least one required human reviewer and restrict deployment branches to `main` and `release-candidate`. Disable administrator bypass.
2. Create the `linger-evaluations` environment, restricted to `main` and `release-candidate`. Add `RELEASE_EVAL_OPENAI_API_KEY`, `RELEASE_EVAL_EXA_API_KEY`, and `RELEASE_EVAL_LOGFIRE_TOKEN`. Use a Logfire token for the synthetic evaluation project. For another provider, add `RELEASE_EVAL_ANTHROPIC_API_KEY` or `RELEASE_EVAL_GOOGLE_API_KEY` instead of the OpenAI key. Keep runtime accounts and memories out of CI.
3. Enable GitHub Packages publication for Actions. The publication job uses its own `GITHUB_TOKEN` with package write permission.
4. If the team later enables automatic publication, create `linger-release-auto`. Restrict deployment branches to `main` and `release-candidate` and leave required human reviewers unset. Keep the protected `linger-release` environment for candidates that need human review.

GitHub runs the automatic `workflow_run` entry point in the default branch's context, `main`. Manual dispatch uses `release-candidate`. Both therefore need environment access, but candidate validation still accepts only successful `release-candidate` push CI. Environment access does not make `main` commits release candidates.

For future dataset changes, use the [Ground truth review skill](../.agents/skills/review-synthetic-ground-truth/SKILL.md). A human must adopt each changed source pair before it enters the release suite. Adoption approves the answer key, not a later model response or release.

## Promote a batch of changes

1. Merge ordinary changes into `main` through the normal PR checks.
2. When the batch is ready, open a PR from `main` to `release-candidate`.
3. Obtain the required approval and merge the promotion PR with **Create a merge commit**. Wait for all CI jobs on the resulting `release-candidate` push to succeed.
4. Open the candidate's **Release checks after candidate promotion** run. With both release switches off, it builds and checks one image without paid calls. Review the build evidence and approve `linger-release` to publish that saved image. The following deployment job verifies public access, deploys its exact digest to the existing Railway service, and retains its deployment ID and readiness results.

A direct candidate push, fork PR, stale candidate, unsuccessful CI, failed publication, or private image cannot deploy through this workflow. Production checks make no model calls. Use **Deploy published image to Railway** on `main` to retry a failed deployment from its original publication run ID and attempt. The retry builds nothing and repeats no evaluations. The [Railway guide](railway.md) covers evidence retention, public package setup, and state preservation.

When live evaluations are enabled, successful candidate CI starts a release run automatically. The run builds a fresh Linux AMD64 image at that commit, scans it, and checks offline startup and persistence before live testing. Approval publishes that tested image without rebuilding it. The promotion's resulting commit SHA is the candidate identity.

## Enable live evaluations

1. Complete the paid evaluation setup above. Railway continues to deploy the published image; the paid suite becomes an additional publication requirement.
2. In `.github/release-config.json`, change `live_evaluations_enabled` to `true`. Leave `auto_publish_enabled` at `false` for human approval of every candidate.
3. Review and merge the configuration change into `main`, then promote it to `release-candidate` with the next batch.
4. Inspect the release run after candidate CI succeeds. Expect paid model calls and synthetic evaluation traces in the configured Logfire project.

To disable live evaluation and publication for new runs, promote a configuration change that sets `live_evaluations_enabled` back to `false`. Manual dispatch reads the current branch configuration even when you select an older candidate SHA. To stop a run already in progress, cancel that run in Actions.

Set the optional repository variables `RELEASE_REPETITIONS` and `RELEASE_MODEL` to change automatic-run defaults. Without them, the workflow uses one repetition and `openai:gpt-6-luna`. These variables do not enable live testing or automatic publication.

## Select a candidate manually

Manual image release dispatch can select a tested candidate for image publication and local use. Production Railway deployment follows the automatic promotion run. To recover a Railway failure, use the deployment-only retry rather than rerunning this image release workflow.

1. Copy the full 40-character SHA of a successful `release-candidate` push CI run. PR builds and `main` builds cannot qualify a release candidate.
2. Open **Actions → Release checks (manual) → Run workflow**. Select `release-candidate` as the workflow branch.
3. Enter the candidate SHA and model. Keep **repetitions** at `1` initially, or enter another positive integer. Every requested repetition counts. Failed observations are never discarded through automatic retries.
4. Inspect the run summary and `release-evidence` artifact. Security failures, invalid adoption, execution errors, missing observations, and missing Logfire evidence block publication. Ordinary behavioral shortfalls remain visible for human review.

The run builds and tests a fresh image at the selected SHA. It saves that image for the approval and publication job in the same run. This image artifact expires after seven days. If it expires before publication, start a new release run and review its new image and evidence.

For a local preflight without model calls, use a clean candidate checkout and its actual Docker image ID:

```bash
	uv run python -m evals.release check \
	  --candidate-sha FULL_COMMIT_SHA \
	  --image-id sha256:FULL_IMAGE_ID \
	  --model openai:gpt-6-luna --repetitions 1 \
	  --output tmp/release-preflight
```

Use a fresh output directory for each command. The candidate SHA must be the full lowercase SHA of the checkout's `HEAD`. `check` validates scenario adoption and configuration but does not verify the supplied local image ID. The GitHub workflow verifies that image before invoking the gate. The optional `--previous-approved PATH` compares counts with an earlier approved `summary.json`. That comparison cannot override a blocker.

To run the paid Scenario suite locally, replace `check` with `run` and choose another output directory. The local command does not read the GitHub live-evaluation switch. It records a publication recommendation, but does not build, scan, publish, or approve an image, or run the separate HTTP smoke. See the [command reference](release-checks.md#release-check-command) for every option and exit status.

## Review and approve a candidate

1. Open the candidate's summary, per-Scene reports, Logfire links, source identities, and HTTP smoke evidence.
2. Review responses for useful grounding, appropriate clarification or decline, citation quality, and unsupported personal claims. Inspect both failed checks and misleading passes.
3. For each attack, confirm that the malicious span reached the agent. Check for paraphrased obedience and unnecessary refusal of the legitimate request. For Line attacks, inspect accepted commits and final personal memories separately from the reply's claims. An absent marker does not prove resistance; a quoted marker does not prove obedience. Review clean comparisons separately from attack resistance.
4. Review ordinary behavioral failures and decide whether they are acceptable for this release. Security and evidence blockers cannot be overridden by this approval.
5. Confirm that the candidate SHA and image ID in the reports match the pending `linger-release` job. Approve the job after completing semantic review.
6. Save `approved-release.json` and the evaluation reports with the project's release records. The record identifies the publication route, registry digest, tested image, and CI run. Human publication also records GitHub's approval history.

With automatic publication off, every eligible candidate waits for approval, including a candidate with a 100% automated pass rate. With paid evaluations disabled, review the offline build, security, persistence, and CI evidence instead; no behavioral pass rate is claimed. Approval publishes the saved Linux AMD64 image to GHCR. Automatic promotion runs then deploy that public digest to Railway. Keep the previous approved digest and publication evidence for recovery.

## Enable optional automatic publication

Keep automatic publication disabled until evaluation results justify a threshold and the team accepts the [automated score's limits](release-checks.md#publication-decision). The configured value of `95` is an uncalibrated placeholder, not an evidence-based release standard.

1. Configure `linger-release-auto` as described above.
2. Set `auto_publish_enabled` to `true` in `.github/release-config.json`.
3. Set `auto_publish_threshold` to the team's evidence-based percentage threshold.
4. Review and promote the configuration change through `main` to `release-candidate`.

With live evaluations enabled and no blockers, a pass percentage strictly greater than the threshold publishes automatically. At or below the threshold, the candidate goes to `linger-release` for human review. At a threshold of `95`, `95%` needs review and `96%` qualifies for automatic publication. Set `auto_publish_enabled` back to `false` to require human approval for every eligible candidate.

The percentage measures automated adopted judgments. It does not establish semantic quality or certify attack resistance. Automatic publication opts into that limitation; semantic-review warnings remain in the evidence. Security failures and incomplete evidence block both publication routes regardless of the threshold.

For failure and approval notifications, enable Actions notifications in your GitHub settings. Inspect failed checks and retained artifacts from the run page. The workflows do not send separate email or chat messages.

## Run an approved image locally

1. Prepare a private environment file from `.env.example`, with the selected provider's key. Keep `LINGER_WEB_SEARCH_ENABLED=false` unless public search is required. Keep `LINGER_DEV_INSPECT=false` for real readers. Set `LOGFIRE_TOKEN` if deployed telemetry is wanted.
2. Set `LINGER_IMAGE` to the approved registry digest. Authenticate to GHCR first if the package is private.
3. Start the image:

```bash
	export LINGER_IMAGE=ghcr.io/desmondchoy/linger@sha256:APPROVED_DIGEST
	export LINGER_ENV_FILE=.env
	docker compose -f compose.release.yaml pull
	docker compose -f compose.release.yaml up -d --no-build --wait
	curl --fail http://127.0.0.1:8080/api/ready
```

Open `http://127.0.0.1:8080`. Sign up or log in, inspect the library, and confirm that an existing conversation is present. Compose binds only to this machine. A shared server also needs a reviewed TLS and network configuration.

The release image targets `linux/amd64`. Docker on Apple Silicon runs this image under emulation, which can be slower than a native image.

To build the combined image locally, `docker compose -f compose.release.yaml build` creates `linger:local`. A local build has not passed the release workflow. The default `compose.yaml` builds the separate backend and frontend services described in the [setup guide](../README.md#start-with-docker-compose).

The release image serves the frontend and backend from one origin and one backend process. Compose explicitly sets `LINGER_STATE_DIR=/var/lib/linger` and `LINGER_MEMORY_DIR=/var/lib/linger/memories`. Accounts, transcripts, declared reading progress, and memories live in the named state volume, while corpus and local model files remain inside the image.

Existing host data is not imported automatically. To move host accounts, transcripts, reading progress, and memories, stop the old process and copy a consistent snapshot into the new state volume with ownership `10001:10001`. Test the snapshot with a disposable volume before using it for real accounts.

## Check an image locally

Run the offline smoke against a built or pulled image:

```bash
	bash docker/smoke.sh linger:local
```

The smoke starts a container with networking disabled and creates a disposable state volume. It checks the frontend, readiness, authentication, account isolation, saved state, restart, and container replacement, then removes its container and volume.

To check rollback compatibility with an approved image, pass that image as the second argument:

```bash
	bash docker/smoke.sh linger:local ghcr.io/desmondchoy/linger@sha256:PREVIOUS_DIGEST
```

Without the second argument, replacement uses the same image and tests persistence across container recreation. For paid HTTP and streaming checks, select `LINGER_MODEL`, export the matching provider key, and run `bash docker/live-smoke.sh IMAGE`. That command uses disposable state and writes `release-evidence/http-smoke.json`.

## Back up state and roll back

1. Stop new traffic and allow active turns to finish. Stop the service with `docker compose -f compose.release.yaml stop`; Compose allows 60 seconds for shutdown.
2. Back up the entire state directory while the service is stopped. Include `accounts.sqlite3`, `transcripts.sqlite3`, `reading_progress.sqlite3`, any `-wal` and `-shm` files, and all memory Markdown and policy files.

```bash
	mkdir -p backups
	docker compose -f compose.release.yaml run --rm --no-deps --user 0 --entrypoint tar \
	  -v "$PWD/backups:/backup" linger \
	  -czf /backup/linger-state-before-rollback.tar.gz -C /var/lib/linger .
```

3. Set `LINGER_IMAGE` to the previous approved digest. Run `docker compose -f compose.release.yaml pull`, then `docker compose -f compose.release.yaml up -d --no-build --wait`.
4. Check `/api/ready`, log in, and verify library access, a saved conversation, and memory access. Check logs before resuming traffic.

Never run `docker compose -f compose.release.yaml down -v` during an update or recovery. That command deletes the state volume. The release workflow has no database migration step. For an incompatible schema change, restore the matching full snapshot into a separate volume and verify it before switching traffic.
