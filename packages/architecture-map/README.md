# Linger architecture map

The shared collaboration map: the component registry, the SVG graph, the curated
evaluation Scenes, and the detail drawer. Two applications render it.

- [`apps/evaluation-explorer`](../../apps/evaluation-explorer) is the standalone
  explorer. It supplies its own page header, footer, and chrome.
- [`apps/frontend`](../../apps/frontend) embeds the graph beside chat, maps live
  turn activity, and uses exported evaluation records for saved playback. Its
  inspector retains every completed turn and opens components in that turn's
  context.

## Consuming it

This package is source-only. It has no build step, no `node_modules`, and no
install of its own; each application aliases `@linger/architecture-map` to
`src/index.ts` in its Vite config and `tsconfig`, and resolves React from its own
dependencies. That keeps both applications independently installable with their
own lockfiles and dev servers.

```ts
import { Graph, Inspector, ScenarioSelect, ScenarioStage, useScenarioExplorer } from '@linger/architecture-map'
import '@linger/architecture-map/src/map.css'
```

`useScenarioExplorer` owns selection and walkthrough state but no layout, so a
host arranges `ScenarioSelect`, `ScenarioStage`, and `Inspector` to suit its own
page. `Graph` renders any `Scene`, which is how the chat panel maps an observed
run rather than a curated one.

## Styling

Every rule in `map.css` is scoped to an `.architecture-map` wrapper, including a
`:where()` reset that keeps a host's own `button` styling from repainting the
graph. Hosts must put `architecture-map` on the element that contains the map.
State classes (`is-explaining`, `status-target`) are matched both on that same
element and on an inner wrapper, so a host may apply `stageClassName` to either.

The map is a light-only design that paints its own cards, so a host with a dark
theme should give it an explicit light plate rather than letting the page show
through.

## Contents

- `types.ts` — component, graph, Scene, and walkthrough contracts.
- `scenarios.ts` — the component registry and every curated Objective route.
- `catalog.json` — generated snapshot of catalog text and archived evaluation
  metadata, read from `synthetic-journal-evaluation/scenarios`.
- `evaluations.json` and `evaluations.ts` — exported evaluation transcripts,
  grades, and playback selection. Available playback depends on this snapshot.
- `layout.ts` — places existing Scene nodes in labelled regions without changing
  their semantics.
- `Graph.tsx`, `Icon.tsx`, `Inspector.tsx`, `ScenarioExplorer.tsx`, `map.css`.

## Validation

Run these commands from the repository root. The standalone explorer owns the
toolchain for this source package:

```sh
pnpm --dir apps/evaluation-explorer test
pnpm --dir apps/evaluation-explorer lint
```

Refresh both data snapshots and check that they match the available source files:

```sh
pnpm --dir apps/evaluation-explorer refresh-data
uv run python apps/evaluation-explorer/scripts/export_catalog.py --check
uv run python apps/evaluation-explorer/scripts/export_evaluations.py --check
```
