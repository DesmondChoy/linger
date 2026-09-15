# Linger architecture map

The shared collaboration map: the component registry, the SVG graph, the curated
evaluation Scenes, and the detail drawer. Two applications render it.

- [`apps/evaluation-explorer`](../../apps/evaluation-explorer) is the standalone
  explorer. It supplies its own page header, footer, and chrome.
- [`apps/frontend`](../../apps/frontend) embeds it in the chat Architecture
  panel, in a *Live turn* mode that maps one real chat turn and an *Explore
  scenarios* mode that reuses the curated explanations unchanged.

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
  records, read from `synthetic-journal-evaluation/scenarios`. Refresh it with
  `pnpm --dir ../../apps/evaluation-explorer refresh-data` and verify with
  `.venv/bin/python apps/evaluation-explorer/scripts/export_catalog.py --check`.
- `layout.ts` — places existing Scene nodes in labelled regions without changing
  their semantics.
- `Graph.tsx`, `Icon.tsx`, `Inspector.tsx`, `ScenarioExplorer.tsx`, `map.css`.

## Validation

Its tests and lint run from the standalone explorer, which owns the toolchain:

```sh
pnpm --dir ../../apps/evaluation-explorer test
pnpm --dir ../../apps/evaluation-explorer lint
```
