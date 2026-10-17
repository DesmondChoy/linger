# Release a Linger version

Use this guide to promote a batch of changes from `main` to `release-candidate`, publish the approved image to GHCR, and deploy it to Railway or run it locally.

Live evaluations and automatic publication are disabled in [`.github/release-config.json`](../.github/release-config.json). At run start, the workflow reads this file from the current `release-candidate` tip. With `live_evaluations_enabled=false`, a release run builds and checks the image, records that live evaluation was intentionally skipped, and waits for human approval. Approval publishes the checked image to GHCR without paid model calls. This route does not require the `linger-evaluations` environment or its secrets.

The [release checks reference](release-checks.md) describes the checks, publication rules, evidence, and limits. Both security datasets have human-approved Ground truth. A release run with live evaluations off produces no new behavioral evaluation evidence.

## Configure GitHub once

These steps need a repository administrator. Repository files cannot configure branch protection, environment reviewers, secrets, or package permissions.

1. Merge the release workflows into `main`. Keep both `live_evaluations_enabled` and `auto_publish_enabled` set to `false`.
2. Keep the existing `release-candidate` branch, or create it from the merged `main` commit if absent. Protect both branches with reviewed, up-to-date pull requests. Enforce the rules for administrators, prohibit direct pushes, and remove PR bypass permissions. Require the seven CI checks listed in the [reference](release-checks.md#ci-checks) on `main`. Require only **Release promotion** on `release-candidate`; full CI runs after the promotion merges. Confirm these protections before using this CI policy. If CodeQL default setup already exists, coordinate its replacement with the advanced workflow.
3. Create the `linger-release` environment. Add at least one required human reviewer and restrict deployment branches to `main` and `release-candidate`. Disable administrator bypass.
4. Enable GitHub Packages publication for Actions. The publication job uses its own `GITHUB_TOKEN` with package write permission.
5. Before enabling live evaluations, create the `linger-evaluations` environment, restricted to `main` and `release-candidate`. Add `RELEASE_EVAL_OPENAI_API_KEY`, `RELEASE_EVAL_EXA_API_KEY`, and `RELEASE_EVAL_LOGFIRE_TOKEN`. Use a Logfire token for the synthetic evaluation project. For another provider, add `RELEASE_EVAL_ANTHROPIC_API_KEY` or `RELEASE_EVAL_GOOGLE_API_KEY` instead of the OpenAI key. Keep runtime accounts and memories out of CI. Skip this setup while live evaluations are disabled.
6. If the team later enables automatic publication, create `linger-release-auto`. Restrict deployment branches to `main` and `release-candidate` and leave required human reviewers unset. Keep the protected `linger-release` environment for candidates that need human review.
7. Complete the [Railway setup](railway.md#configure-github-once) for the existing production service. Railway Hobby requires the GHCR package to be public.

GitHub runs the automatic `workflow_run` entry point in the default branch's context, `main`. Manual dispatch uses `release-candidate`. Both therefore need environment access, but candidate validation still accepts only successful `release-candidate` push CI. Environment access does not make `main` commits release candidates. Both evaluation modes require a correctly protected `linger-release` environment.

For future dataset changes, use the [Ground truth review skill](../.agents/skills/review-synthetic-ground-truth/SKILL.md). A human must adopt each changed source pair before it enters the release suite. Adoption approves the answer key, not a later model response or release.

## Promote a batch of changes

1. Merge ordinary changes into `main` through the normal PR checks.
2. [Synchronize the branch history](#synchronize-the-branch-history) if `release-candidate` is not an ancestor of `main`.
3. When the batch is ready, open a PR from `main` to `release-candidate`.
4. Review the promotion PR and wait for **Release promotion** to pass. The full CI jobs are skipped on this PR. Select **Create a merge commit**, then wait for full CI on the resulting `release-candidate` push to succeed.
5. Open the candidate's **Release checks after candidate promotion** run. Inspect the candidate validation, image build, Trivy report, and offline startup and persistence checks.
6. With live evaluations off, inspect `release-image-evidence-<sha>-<run>-<attempt>`. Confirm that `behavioral/summary.json` records `status: skipped` and `publication.score_scope: not_evaluated`. Its behavioral pass percentage and judgment counts must be `null`.
7. Complete [review and approval](#review-and-approve-a-candidate). Approve the pending `linger-release` job to publish the checked image to GHCR.
8. Inspect the Railway deployment in the same run. It consumes the publication artifact and deploys its exact image digest. Follow the [Railway guide](railway.md) for the first public-package setup, verification, or a deployment-only retry.

Successful candidate CI starts a release run in either mode. The run builds one fresh Linux AMD64 image at the candidate commit, scans it, and checks offline startup and persistence. When enabled, live evaluations follow those checks. Publication uses the saved image without rebuilding it. The promotion's resulting commit SHA is the candidate identity.

To stop a release, cancel its Actions run before publication. Setting `live_evaluations_enabled=false` selects publication with human approval and no live evaluation. It does not disable publication or cancel a run.

### Synchronize the branch history

Both protected branches require the PR branch to include the destination's current history. A promotion merge adds a commit to `release-candidate` that `main` does not yet contain. Before the next promotion, merge that history back through a reviewed PR into `main`.

1. Use a clean checkout and fetch both branches:

```bash
	git fetch origin
	git merge-base --is-ancestor origin/release-candidate origin/main
```

2. If the ancestry check exits `0`, continue with promotion. If it exits `1`, create a temporary branch from the current `main` and merge `release-candidate`. Choose a unique branch name:

```bash
	git switch -c codex/sync-release-candidate-YYYYMMDD origin/main
	git merge --no-ff origin/release-candidate
	git push -u origin HEAD
```

3. Open a PR from the synchronization branch to `main`. Resolve conflicts, obtain review, and wait for required CI to pass. If `main` advances, merge its updated history into the synchronization branch and rerun the required checks.
4. Merge the synchronization PR with **Create a merge commit**. This preserves the `release-candidate` ancestry in `main`.
5. Open the promotion PR from `main` to `release-candidate`. Merge that PR with **Create a merge commit** after review and a successful **Release promotion** check. Full CI runs on the resulting commit before release.

Use merge commits for both PRs. Squash or rebase merging loses the ancestry needed by the next promotion. Start the synchronization branch from current `main`, because a direct PR from `release-candidate` can be behind `main` after feature merges. The synchronization PR runs ordinary CI on `main`; the subsequent promotion starts the release flow.

## Enable live evaluations

1. Complete the GitHub setup above.
2. In `.github/release-config.json`, change `live_evaluations_enabled` to `true`. Leave `auto_publish_enabled` at `false` for human approval of every candidate.
3. Review and merge the configuration change into `main`, then promote it to `release-candidate` with the next batch.
4. Inspect the release run after candidate CI succeeds. Expect paid model calls and synthetic evaluation traces in the configured Logfire project.

To skip paid evaluations in new runs, promote a configuration change that sets `live_evaluations_enabled` back to `false`. New runs still build and check an image, then require human approval for publication. Manual dispatch reads the current branch configuration even when you select an older candidate SHA. To stop a run already in progress, cancel that run in Actions.

Set the optional repository variables `RELEASE_REPETITIONS` and `RELEASE_MODEL` to change automatic-run defaults. Without them, the workflow uses one repetition and `openai:gpt-6-luna`. These variables do not enable live testing or automatic publication.

## Select a candidate manually

Use manual dispatch to select a candidate in either evaluation mode.

1. Copy the full 40-character SHA of a successful `release-candidate` push CI run. PR builds and `main` builds cannot qualify a release candidate.
2. Open **Actions → Release checks (manual) → Run workflow**. Select `release-candidate` as the workflow branch.
3. Enter the candidate SHA and model. Keep **repetitions** at `1` initially, or enter another positive integer. The model and repetition inputs apply when live evaluations are enabled.
4. Inspect the run summary and `release-image-evidence-<sha>-<run>-<attempt>`. A failed candidate, configuration, image, security, or offline smoke check blocks publication in either mode.
5. If live evaluations are enabled, also inspect `release-evidence-<sha>-<run>-<attempt>`. Every requested repetition counts. Invalid adoption, execution errors, missing observations, and missing Logfire evidence block publication. Ordinary behavioral shortfalls remain visible for human review. Failed evaluation never falls back to the skipped-evaluation route.
6. Complete [review and approval](#review-and-approve-a-candidate). With live evaluations off, human approval is required even if `auto_publish_enabled=true`.

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

1. Open the candidate summary and common image evidence. Check the successful candidate CI, configuration snapshot, image identity, Trivy report, and offline startup and persistence results.
2. If evaluation was intentionally skipped, confirm that the configuration disables live evaluations and the summary makes no behavioral pass claim. Decide whether to publish with that stated limitation. No live provider, Scenario, or HTTP inference evidence exists for this run.
3. If evaluation completed, open the per-Scene reports, Logfire links, source identities, and HTTP smoke evidence. Review responses for useful grounding, appropriate clarification or decline, citation quality, and unsupported personal claims. Inspect failed checks and misleading passes.
4. For each evaluated attack, confirm that the malicious span reached the agent. Check for paraphrased obedience and unnecessary refusal of the legitimate request. For Line attacks, inspect accepted commits and final personal memories separately from the reply's claims. An absent marker does not prove resistance. A quoted marker does not prove obedience. Review clean comparisons separately from attack resistance.
5. Review any ordinary behavioral failures and decide whether they are acceptable for this release. Security and evidence blockers cannot be overridden by approval.
6. Confirm that the candidate SHA, configuration SHA, and image ID match the pending `linger-release` job. Approve that job after completing the applicable review.
7. Save `publication.json`, `approved-release.json`, and the evidence with the project's release records. In `publication.json`, `evaluation_status` is `skipped` or `completed`. The same authorization appears under `authorization` in `approved-release.json`, alongside the published digest, image identity, and CI run. Human publication also records GitHub's approval history.

With live evaluations off, every eligible candidate waits for approval regardless of the automatic-publication setting. With live evaluations on and automatic publication off, every eligible candidate also waits, including one with a 100% automated pass rate. Approval publishes the saved Linux AMD64 image to GHCR. The automatic promotion run then deploys its immutable digest to the existing Railway service. A manual candidate run leaves deployment to the operator. Keep the previous approved digest available for recovery.

For a Railway failure after successful publication, use [Retry deployment without rebuilding](railway.md#retry-deployment-without-rebuilding). Select the original publication run and attempt. The retry reuses the retained evidence and published image without rebuilding, republishing, or rerunning evaluations.

## Enable optional automatic publication

Keep automatic publication disabled until evaluation results justify a threshold and the team accepts the [automated score's limits](release-checks.md#publication-decision). The configured value of `95` is an uncalibrated placeholder, not an evidence-based release standard.

1. Configure `linger-release-auto` as described above.
2. Set `auto_publish_enabled` to `true` in `.github/release-config.json`.
3. Set `auto_publish_threshold` to the team's evidence-based percentage threshold.
4. Review and promote the configuration change through `main` to `release-candidate`.

With live evaluations enabled and no blockers, a pass percentage strictly greater than the threshold publishes automatically. At or below the threshold, the candidate goes to `linger-release` for human review. At a threshold of `95`, `95%` needs review and `96%` qualifies for automatic publication. With live evaluations disabled, no score exists and human approval is always required. Set `auto_publish_enabled` back to `false` to require human approval for every eligible candidate with completed evaluations.

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
