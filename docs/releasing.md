# Release a Linger version

Use this guide to promote a version from `main` to `release-candidate`, run live evaluations, publish the approved image to GHCR, and deploy it to Railway or run it locally.

Live evaluations and automatic publication are enabled in [`.github/release-config.json`](../.github/release-config.json). The settings take effect after promotion to `release-candidate`. At run start, the workflow reads this file from the current `release-candidate` tip and saves its exact configuration commit. A change on `main` alone does not change the release settings. The workflow keeps the saved configuration for that run.

The [release checks reference](release-checks.md) describes the checks, publication rules, evidence, and limits. Both security datasets have human-approved Ground truth. Enabled switches permit automatic execution; they do not establish that the hosted release has passed or that a threshold is calibrated.

## Configure GitHub once

These steps need a repository administrator. Repository files cannot configure branch protection, environment reviewers, secrets, or package permissions.

1. Merge the release workflows into `main`. Complete these settings before promoting enabled release controls to `release-candidate`.
2. Keep the existing `release-candidate` branch, or create it from `main` if absent. Require reviewed PRs on both branches. Enforce the rules for administrators, prohibit direct pushes, and remove PR bypass permissions. Require up-to-date PRs and the seven CI checks listed in the [reference](release-checks.md#ci-checks) on `main`. On `release-candidate`, require only **Release promotion** and leave **Require branches to be up to date before merging** disabled. Full CI runs on the exact candidate commit after merge. Block force pushes and branch deletion on both branches. If CodeQL default setup already exists, coordinate its replacement with the advanced workflow.
3. Create the `linger-release` environment. Add at least one required human reviewer and restrict deployment branches to `main` and `release-candidate`. Disable administrator bypass.
4. Enable GitHub Packages publication for Actions. The publication job uses its own `GITHUB_TOKEN` with package write permission.
5. Create the `linger-evaluations` environment, restricted to `main` and `release-candidate`, with required human reviewers unset for unattended execution. Add `RELEASE_EVAL_OPENAI_API_KEY`, `RELEASE_EVAL_EXA_API_KEY`, and `RELEASE_EVAL_LOGFIRE_TOKEN`. Use a Logfire token for the synthetic evaluation project. For another provider, add `RELEASE_EVAL_ANTHROPIC_API_KEY` or `RELEASE_EVAL_GOOGLE_API_KEY` instead of the OpenAI key. Keep runtime accounts and memories out of CI.
6. Create `linger-release-auto`. Restrict deployment branches to `main` and `release-candidate` and leave required human reviewers unset. Keep the protected `linger-release` environment for candidates that need human review.
7. Complete the [Railway setup](railway.md#configure-github-once) for the existing production service. Configure `railway-production` for `main` only, without required reviewers for unattended deployment, and add its `RAILWAY_TOKEN` secret. Keep Railway's separate GitHub auto-deploys and image auto-updates disabled.
8. Verify Actions can publish the GHCR package and Railway can pull it publicly. If this is the first publication, complete the [public-package setup](railway.md#make-the-ghcr-package-public), then retry only deployment. A first package created as private prevents an uninterrupted first run.

GitHub runs the automatic `workflow_run` entry point in the default branch's context, `main`. Manual dispatch uses `release-candidate`. Both therefore need environment access, but candidate validation still accepts only successful `release-candidate` push CI. Environment access does not make `main` commits release candidates. Both evaluation modes require a correctly protected `linger-release` environment.

For future dataset changes, use the [Ground truth review skill](../.agents/skills/review-synthetic-ground-truth/SKILL.md). A human must adopt each changed source pair before it enters the release suite. Adoption approves the answer key, not a later model response or release.

## Run the full automatic flow

1. Verify the administrator setup above. In `.github/release-config.json`, confirm that `live_evaluations_enabled` and `auto_publish_enabled` are `true`, and review `auto_publish_threshold`.
2. Merge the version's code and configuration changes into `main` through reviewed PRs. Full CI runs on those PRs. Merging into `main` runs CodeQL only and does not start live release evaluations.
3. Open a promotion PR from this repository's `main` to `release-candidate`.
4. Obtain review and wait for **Release promotion** to pass. The full CI jobs are skipped on this PR. Select **Create a merge commit**, then wait for full CI on the resulting `release-candidate` push to succeed.
5. Open the candidate's **Release checks after candidate promotion** run. Inspect candidate validation, the configuration snapshot, the image build, the Trivy report, and the offline startup and persistence checks.
6. Inspect `release-evidence-<sha>-<run>-<attempt>`. The live suite runs six Scenarios containing 22 Scenes per repetition, followed by two live HTTP turns in the same release image. Check the behavioral summary, per-Scene reports, Logfire links, and `http-smoke.json`.
7. Check the publication decision. With no blockers and a score strictly above the configured threshold, `linger-release-auto` publishes without human approval. At or below the threshold, complete [review and approval](#review-and-approve-a-candidate) through `linger-release`. Security failures, evaluation crashes, and missing or invalid required evidence stop publication. Human approval cannot override them.
8. Inspect `release-publication-<sha>-<run>-<attempt>` and `railway-deployment-<run>-<attempt>`. Confirm the candidate commit, configuration commit, checked image ID, published registry digest, and Railway deployment agree. The deployment must be active, serve the website, and pass `/api/ready`.

Successful candidate CI starts a release run in either mode. The run builds one fresh Linux AMD64 image at the candidate commit, scans it, and checks offline startup and persistence. The live Scenario suite uses the candidate checkout and local model files copied from that image. Live HTTP checks run inside the image. Publication uses the saved image without rebuilding it, and Railway deploys its immutable registry digest. The promotion's resulting commit SHA is the candidate identity.

Promote each new version from `main` to `release-candidate`. Routine promotion does not require merging `release-candidate` back into `main`. If GitHub requires that history update, ask an administrator to correct the candidate branch's up-to-date requirement. Resolve genuine code conflicts before promotion.

Set the optional repository variables `RELEASE_REPETITIONS` and `RELEASE_MODEL` to change automatic-run defaults. Without them, the workflow uses one repetition and `openai:gpt-6-luna`. These variables do not enable live testing or automatic publication. Live evaluation and HTTP inference make paid provider calls.

For the first GHCR package or a Railway-only failure, follow [Retry deployment without rebuilding](railway.md#retry-deployment-without-rebuilding). Reuse the successful publication run and attempt to avoid repeating paid evaluations.

## Disable automatic release after the trial

1. Cancel any running or waiting release runs that must not continue. A configuration change cannot change a run's saved settings or undo a completed publication or deployment.
2. Set both `live_evaluations_enabled` and `auto_publish_enabled` to `false` in `.github/release-config.json`. Keep the threshold for a later trial.
3. Review and merge that change into `main`, then promote `main` to `release-candidate` through a reviewed PR with **Create a merge commit**.
4. Confirm the next release run records both switches as `false` in its configuration snapshot. The new run still builds and checks an image, then waits for human approval. Cancel that run if no further publication is wanted.

With live evaluations disabled, inspect `release-image-evidence-<sha>-<run>-<attempt>`. Its `behavioral/summary.json` records `status: skipped`, `publication.score_scope: not_evaluated`, and `null` judgment counts and percentage. It does not claim a passing evaluation. The `linger-evaluations` environment and its secrets are unused in this mode.

Disabling both switches stops paid evaluations and automatic publication in new runs. Human approval can still publish the checked image and, for a promotion run, deploy it to Railway. The workflow reads controls from the current `release-candidate` tip, including when a manual dispatch selects an older candidate. Old runs retain their original snapshots until cancelled.

## Select a candidate manually

Use manual dispatch to select a candidate in either evaluation mode.

1. Copy the full 40-character SHA of a successful `release-candidate` push CI run. PR builds and `main` builds cannot qualify a release candidate.
2. Open **Actions → Release checks (manual) → Run workflow**. Select `release-candidate` as the workflow branch.
3. Enter the candidate SHA and model. Keep **repetitions** at `1` initially, or enter another positive integer. The model and repetition inputs apply when live evaluations are enabled.
4. Inspect the run summary and `release-image-evidence-<sha>-<run>-<attempt>`. A failed candidate, configuration, image, security, or offline smoke check blocks publication in either mode.
5. If live evaluations are enabled, also inspect `release-evidence-<sha>-<run>-<attempt>`. Every requested repetition counts. Security violations, a crashed replay process, and missing or invalid required evidence block publication. A completed replay can record failed agent tasks without blocking. Those failed judgments remain in the score. See the [publication policy](release-checks.md#publication-decision) for the distinction. Failed evaluation never falls back to the skipped-evaluation route.
6. Check the selected publication route. If it is `manual`, complete [review and approval](#review-and-approve-a-candidate). If it is `automatic`, publication proceeds through `linger-release-auto` without human approval. Manual dispatch selects the candidate; it does not force manual publication. With live evaluations off, human approval is required even if `auto_publish_enabled=true`.

The run builds and tests a fresh image at the selected SHA. It saves that image for the approval and publication job in the same run. This image artifact expires after seven days. If it expires before publication, start a new release run and review its new image and evidence.

Manual candidate selection publishes an image for operator deployment. Railway's automatic deployment and deployment-only retry accept evidence from **Release checks after candidate promotion**. Use the promotion flow to release through Railway.

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

Use these steps when the publication decision selects the `manual` route and the run waits for `linger-release` approval.

1. Open the candidate summary and common image evidence. Check the successful candidate CI, configuration snapshot, image identity, Trivy report, and offline startup and persistence results.
2. If evaluation was intentionally skipped, confirm that the configuration disables live evaluations and the summary makes no behavioral pass claim. Decide whether to publish with that stated limitation. No live provider, Scenario, or HTTP inference evidence exists for this run.
3. If evaluation completed, open the per-Scene reports, Logfire links, source identities, and HTTP smoke evidence. Review responses for useful grounding, appropriate clarification or decline, citation quality, and unsupported personal claims. Inspect failed checks and misleading passes.
4. For each evaluated attack, check its adopted handling: agent-resistance cases require the malicious span to reach the agent; explicit application-guard cases require a verified input block without agent calls or writes. These are separate claims. Check for paraphrased obedience and unnecessary refusal of the legitimate request. For Line attacks, inspect accepted commits and final personal memories separately from the reply's claims. An absent marker does not prove resistance. A quoted marker does not prove obedience. Review clean comparisons separately from attack resistance.
5. Review any ordinary behavioral failures and decide whether they are acceptable for this release. Security failures, evaluation crashes, and missing or invalid required evidence cannot be overridden by approval.
6. Confirm that the candidate SHA, configuration SHA, and image ID match the pending `linger-release` job. Approve that job after completing the applicable review.
7. Save `publication.json`, `approved-release.json`, and the evidence with the project's release records. In `publication.json`, `evaluation_status` is `skipped` or `completed`. The same authorization appears under `authorization` in `approved-release.json`, alongside the published digest, image identity, and CI run. Human publication also records GitHub's approval history.

With live evaluations off, every eligible candidate waits for approval regardless of the automatic-publication setting. With live evaluations on and automatic publication off, every eligible candidate also waits, including one with a 100% automated pass rate. Approval publishes the saved Linux AMD64 image to GHCR. The automatic promotion run then deploys its immutable digest to the existing Railway service. A manual candidate run leaves deployment to the operator. Keep the previous approved digest available for recovery.

For a Railway failure after successful publication, use [Retry deployment without rebuilding](railway.md#retry-deployment-without-rebuilding). Select the original publication run and attempt. The retry reuses the retained evidence and published image without rebuilding, republishing, or rerunning evaluations.

## Review a failed live evaluation

Use the [publication policy](release-checks.md#publication-decision) to distinguish a failed task from a release blocker.

1. Open the run's `behavioral/summary.json` and inspect `blocking_failures`, `behavioral_failures`, and raw `execution_failures`.
2. Check that the replay process completed successfully and retained every required Scene, judgment, source identity, and Logfire observation. Resolve a crashed process or missing evidence before retrying the release.
3. Inspect security blockers against the released reply, actual tool activity, and storage observations. Fix an unauthorized disclosure, source access, release, or memory change before retrying.
4. Review ordinary task failures against the adopted expectations. Keep failed judgments in the score. A rejected tool call, missing retrieval, refused response, or unsuccessful model attempt can remain a quality failure when the completed replay has valid evidence.
5. Check the publication route against the configured threshold. Complete the manual review when that route requires approval. Record quality defects for follow-up.

New quality failure codes need no allowlist entry or fallback exemption. Unknown artifact schemas and incomplete observations still block as invalid evidence. If a grader uses one code for both a rejected candidate and an actual unauthorized release, split those outcomes and test each classification. The owning [release reference](release-checks.md#publication-decision) describes the blocker categories and required evidence.

Retain the original evaluation files and candidate identities. Offline reclassification helps diagnose policy changes. It does not replace a release run for the selected candidate or establish that publication succeeded.

## Adjust automatic publication

Review the configured threshold against past results and the [automated score's limits](release-checks.md#publication-decision). Enabling the route does not calibrate the threshold or prove live response quality.

1. To change the automatic decision, edit `auto_publish_threshold` in `.github/release-config.json`.
2. To require human approval while retaining paid evaluations, set `auto_publish_enabled` to `false` and keep `live_evaluations_enabled` at `true`.
3. Review and promote the configuration change through `main` to `release-candidate`.

With live evaluations and automatic publication enabled and no blockers, a pass percentage strictly greater than the threshold publishes automatically. At or below the threshold, the candidate goes to `linger-release` for human review. The comparison uses exact judgment counts, not the rounded display percentage. With live evaluations disabled, no score exists and human approval is always required.

The percentage measures automated adopted judgments. It does not establish semantic quality or certify attack resistance. Automatic publication opts into that limitation; semantic-review warnings remain in the evidence. Security failures, evaluation crashes, and missing or invalid required evidence block both publication routes regardless of the threshold.

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
