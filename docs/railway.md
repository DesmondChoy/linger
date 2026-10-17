# Deploy Linger on Railway

Deploy the website and Python API together from source with Railway's Railpack
builder. Visitors open one HTTPS URL. FastAPI serves the built React files and
handles `/api` requests on the same origin.

The current website is [Linger](https://linger-production-b81b.up.railway.app).
Its [Railway project](https://railway.com/project/6db691f2-f510-4018-aaaf-4be0ddef2b8a)
uses the `production` environment and `linger` service.

The build uses [`railpack.json`](../railpack.json) to install Python and Node,
build the frontend, and download the embedding and reranking models. Startup
uses those packaged models with Hugging Face network access disabled.
No local Docker installation is required.

## Configure the service

1. Create a Railway project and an empty service named `linger`.
2. Select **Railpack** as the builder. Keep the root directory at the repository
   root and leave custom build and start commands empty.
3. Attach a persistent volume named `linger-state` at `/var/lib/linger`.
4. Use one replica in Singapore, with limits of 2 vCPUs and 2 GB RAM. The
   application runs one Uvicorn worker because
   active sessions and rate limits are held in process memory.
5. Set the healthcheck path to `/api/ready` and its timeout to `600` seconds.
   Use **On Failure** with five restart attempts and a 60-second draining period.
6. Add these private service variables:

| Variable | Value |
| --- | --- |
| `LINGER_MODEL` | `openai:gpt-6-luna` |
| `OPENAI_API_KEY` | An OpenAI provider key |
| `LINGER_WEB_SEARCH_ENABLED` | `true` |
| `EXA_API_KEY` | An Exa key for public-web search |
| `LINGER_DEV_INSPECT` | `false` |
| `PORT` | `8000` |

The build configuration sets the frontend, model-cache, state, and memory paths.
Accounts, transcripts, reading progress, and account memories live on the
volume. Corpus files and local models remain in the application build.

## Deploy the source

Install the [official Railway CLI](https://docs.railway.com/cli), then run these
commands from the repository root:

```sh
	railway login
	railway link --project PROJECT_ID --environment production --service linger
	railway up --detach --message "Deploy Linger website"
```

[`.railwayignore`](../.railwayignore) limits the upload to application source,
the corpus, and build configuration. Local credentials, databases, memories,
reports, development environments, and Docker build files are excluded.
The initial deployment uses CLI uploads. A Git push does not deploy the service.
Run `railway up` again after a verified update.

Generate a Railway domain with target port `8000`:

```sh
	railway domain --port 8000
```

## Verify a deployment

Check the public website and API:

```sh
	curl --fail https://YOUR_DOMAIN/
	curl --fail https://YOUR_DOMAIN/api/health
	curl --fail https://YOUR_DOMAIN/api/ready
```

Readiness checks provider configuration, writable state, database integrity,
corpus files, model checksums, local inference, and the built frontend.
It returns `{"status":"ready"}` after those checks pass.

Create a test account through the website and send this book question:

> I have finished Chapter 3 of Alice's Adventures in Wonderland. What does the
> Dodo announce about the winners and prizes?

Confirm that a reply and book sources appear. Reload the page to check that the
conversation is saved. Restart the Railway service, then sign in again and
verify that the account and conversation remain.

The existing reading-progress parser can reject declarations with trailing
clauses or a title and progress in separate sentences. Bead `linger-6ts5`
tracks the two forms found during deployment verification. Keep the completed
chapter and book title together as in the example above until that bug is fixed.

The existing prototype has open signup and no password reset, email
verification, or login lockout. Provider usage is charged to the configured
keys. Review Railway resource usage and provider usage before sharing the URL
beyond the intended testers.

## Preserve state during updates

Keep `linger-state` attached at `/var/lib/linger` when redeploying or restarting.
Volume-backed deployments have a short interruption while Railway moves the
volume to the new process. Back up the volume before changes to database
schemas or stored memories. See [Railway volume backups](https://docs.railway.com/volumes/backups).
