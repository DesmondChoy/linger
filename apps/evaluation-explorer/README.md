# Linger evaluation explorer

A separate React app for exploring Linger's multi-agent architecture through evaluation Objectives and illustrative Scenes. The light interface keeps the collaboration map visible and reveals inputs, agent roles, handoff payloads, criteria, and archived evidence on demand.

## Run locally

From this directory:

```sh
pnpm install --frozen-lockfile
pnpm dev
```

Open [the explorer](http://127.0.0.1:5184). It has its own package manifest, lockfile, Vite server, and build output. It does not import `apps/frontend`, proxy the backend, invoke providers, or start evaluations.

```sh
pnpm test
pnpm lint
pnpm build
pnpm preview
```

The production preview runs on [port 4184](http://127.0.0.1:4184). Pass `--port <number>` to `pnpm dev` if the default port is occupied.

## Explore

Select an Objective, then a Scene. The map updates immediately. Hover over a component for a short description, or click a component or connection to inspect its role and bounded handoff. All connections also support keyboard focus and Enter or Space.

Agent cards contain their names and roles, while labeled regions distinguish retrieval, conversation, capture, and curation. The map preserves readable text sizes instead of shrinking to fit a small viewport.

“Explain step by step” highlights the expected sequence. Next and Previous, or the right and left arrow keys, move through it. Escape exits and returns focus to the explanation button. On narrow screens, swipe the map horizontally; the guided explanation follows the active components and centers the destination when a step spans more than the visible area. Short landscape screens place the explanation beside the map.

The default map explains expected architecture. A target badge and dashed connections identify incomplete workflows. The curation component view ends at Sculptor's proposal or no-change output. Ground truth stays outside the runtime, and archived History records do not change the expected map into an observed execution trace.

## Data and ownership

- `src/scenarios.ts` owns the curated visual explanations and walkthroughs. It covers all catalog Objectives and cites implementation limits in each Scene. These illustrative inputs are separate from generated package data.
- `src/catalog.json` is a generated snapshot of catalog text and minimal package/run metadata. It includes recorded failure codes without inferring a pass from missing failures. It does not bundle private credentials, raw application memory, or complete transcripts.
- `src/layout.ts` positions existing Scene nodes within labeled regions without changing their semantics. `src/Graph.tsx` renders the map; `src/Inspector.tsx` handles progressive disclosure. `src/App.tsx` owns selection and walkthrough state.

Refresh the snapshot after the catalog or package records change, using the repository Python environment:

```sh
pnpm refresh-data
../../.venv/bin/python scripts/export_catalog.py --check
../../.venv/bin/python -m pytest -q scripts/test_export_catalog.py
```

Review affected Scene routes against `docs/specification.md` and the maintained implementation after contract changes. The exporter updates catalog text and recorded evidence; it does not infer architecture from telemetry or silently revise the explanations.
