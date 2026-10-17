# Deploy Linger on Railway

The website and Python API run together at
[Linger](https://linger-production-b81b.up.railway.app). FastAPI serves the built
React files and `/api` requests from one origin.

Production uses the existing [Linger Railway project](https://railway.com/project/6db691f2-f510-4018-aaaf-4be0ddef2b8a),
its `production` environment, `linger` service, and `linger-state` volume.

## Promote and deploy a release

1. Merge feature PRs into `main` after review and CI.
2. [Synchronize the branch history](releasing.md#synchronize-the-branch-history)
   if `release-candidate` is not an ancestor of `main`. Complete this step before
   each subsequent promotion.
3. Open a promotion PR from this repository's `main` to `release-candidate`.
4. Obtain the required approval and use **Create a merge commit**. Both branches
   require the seven application and security checks. `release-candidate` also
   requires **Release promotion** to verify the PR source.
5. Wait for CI on the resulting `release-candidate` commit to succeed.
6. Open **Release checks after candidate promotion**. The release job builds one
   Linux AMD64 image, scans it, and checks offline startup and persistent state.
   It saves that image for publication. Paid evaluations stay disabled in
   [`.github/release-config.json`](../.github/release-config.json).
7. Review the retained build evidence and approve **linger-release**. The publish
   job loads and publishes the saved image to `ghcr.io/desmondchoy/linger`, without
   rebuilding. Its `approved-release.json` records the immutable image digest,
   candidate commit, CI run, and publication authorization. The authorization's
   `evaluation_status` is `skipped` while live evaluations are disabled.
8. The deployment job verifies that the exact image can be pulled anonymously,
   updates the existing Railway service's image source, and deploys it. Railway
   runs the published image directly.
9. Inspect the `railway-deployment` artifact. The job waits for the specific new
   deployment ID, verifies its image digest and state mount, confirms it is
   active on the existing service, and checks public HTML and `/api/ready`.

Live evaluations and automatic publication are currently disabled. Disabled live
evaluations always require human publication approval, including when the
automatic-publication switch is enabled. The behavioral summary records
`status: skipped`, `publication.score_scope: not_evaluated`, and `null` scores.
Enabling paid evaluations adds the existing live evidence requirements before
publication. Post-deployment HTTP checks make no model or search calls.

Railway consumes `release-publication-<sha>-<run>-<attempt>`, produced by the
existing [publication workflow](release-checks.md#triggers-and-approval).
The deployment helper reuses its publication validator to check the saved
configuration, image checks, behavioral summary, and authorization. Publication
remains responsible for the approval decision and the tested image.

The source, offline smoke, image scan, optional live checks, and publication all
refer to the same saved release image. The separate image built by ordinary CI
is discarded. Production uses the image checked by the release workflow.

## Make the GHCR package public

Railway Hobby can pull public images. It cannot use private registry credentials.
GitHub creates the first GHCR package as private even when its source repository
is public. [GitHub visibility documentation](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
explains the package setting.

After the first approved publication:

1. Open the [Linger container package](https://github.com/DesmondChoy/linger/pkgs/container/linger).
2. Open **Package settings**, then **Change visibility** and choose **Public**.
   Public visibility cannot be reversed. The image contains application source,
   corpus, and packaged models; runtime provider keys, accounts, and memories
   remain outside the image.
3. Run the deployment-only retry below using that publication's run ID and
   attempt. The anonymous-pull guard refuses to change Railway while the image
   is private or unavailable.

Use the recorded `ghcr.io/desmondchoy/linger@sha256:...` reference. Mutable tags
such as `latest` do not identify an approved release.

## Retry deployment without rebuilding

Use **Actions → Deploy published image to Railway → Run workflow** on `main`.
Enter the original automatic release run ID and the attempt that successfully
published the image. The default attempt is `1`.

The retry downloads that attempt's retained publication evidence. It verifies
that the publication job succeeded even if the overall run failed during
Railway deployment. It then rechecks the current candidate tip, successful push
CI, merged promotion PR, approval, and anonymous registry access. It runs no image
build, publication, model evaluation, or paid HTTP smoke.

Automatic deployments and retries share the `railway-production` concurrency
group. A retry cannot replace a newer release candidate. Publication evidence is
retained for 30 days; expired evidence prevents a retry. Keep approved release
records before their expiry. Do not rerun the whole release workflow to recover
from a Railway-only failure.

## Configure GitHub once

1. Protect `main` and `release-candidate` with one required approval, dismissal of
   stale approvals, up-to-date required CI checks, and administrator enforcement.
   Block force pushes and branch deletion. Require **Release promotion** on
   `release-candidate` as well.
2. Configure required human reviewers on **linger-release**. Permit `main` and
   `release-candidate` workflow contexts for image publication.
3. Configure **railway-production** to allow `main` only. Automatic `workflow_run`
   jobs and deployment-only retries execute trusted helpers from the protected
   default branch, while validating the candidate commit independently.
4. Store a Railway project token scoped to Linger's `production` environment as
   the **environment secret** `RAILWAY_TOKEN` in `railway-production`.
5. Merge PR #107 into `main`, then promote `main` to `release-candidate`. Keep
   Railway GitHub auto-deploys and image auto-updates disabled so they cannot
   bypass successful publication and the selected immutable digest.

## Preserve the existing service and state

Keep the service at one replica in Singapore, with limits of 2 vCPUs and 2 GB RAM.
Keep the volume `da3aff80-4c28-42c3-8317-5eb51fc85c7c` attached to service
`7283294a-c4d8-4908-b7ae-8c5e2fa40913` at `/var/lib/linger`. Keep `/api/ready` as the
healthcheck path, its timeout at 600 seconds, On Failure with five restart
attempts, and a 60-second draining period.

The deployment helper checks the project has only its expected production
environment because Railway's instance update can propagate to other non-fork
environments. Review that isolation check before adding environments.

The previous Railpack build may leave root-owned state. The workflow saves
`RAILWAY_RUN_UID=0` without triggering a deployment, then switches the image.
The image entrypoint repairs ownership only inside the state directory, drops to
UID and GID `10001`, and starts the application. The application runs without
root privileges. The image smoke checks this migration using populated,
root-owned state and verifies persistence across restart and replacement.

Keep these private service variables:

| Variable | Value |
| --- | --- |
| `LINGER_MODEL` | `openai:gpt-6-luna` |
| `OPENAI_API_KEY` | An OpenAI provider key |
| `LINGER_WEB_SEARCH_ENABLED` | `true` |
| `EXA_API_KEY` | An Exa key for public-web search |
| `LINGER_DEV_INSPECT` | `false` |
| `PORT` | `8000` |

The image defines the model-cache, frontend, state, and memory paths. Keep custom
start commands empty so the image entrypoint and command run. Never copy the old
Railpack model or frontend paths into service-variable overrides.

Accounts, transcripts, reading progress, and account memories remain on the
volume. Corpus files and packaged models remain in the image. Volume-backed
updates have a short interruption while Railway moves the volume to the new
process. Back up state before a schema or memory-storage change. See
[Railway volume backups](https://docs.railway.com/volumes/backups).
