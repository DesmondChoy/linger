import type { ComponentId, GraphEdge, GraphNode, Scene, WalkthroughStep } from '@linger/architecture-map'
import type { ProgressEvent, TurnRecord } from '../../types'
import { formatMachineLabel } from '../formatMachineLabel'

export type ActivityStatus = 'running' | 'complete' | 'declined' | 'failed'

export type ComponentActivity = {
  id: ComponentId
  status: ActivityStatus
  /** Every stage this component ran, in the order the server reported them. */
  stages: { stage: string; status: ActivityStatus; elapsedMs: number }[]
}

export type LiveTurn = {
  scene: Scene
  /** Components that have done something, keyed by component id. */
  activity: ComponentActivity[]
  /** Components still running, shaped for the map's highlight mechanism. */
  active: WalkthroughStep | null
  running: boolean
}

/**
 * Which map components one allowlisted progress stage exercises.
 *
 * Serendipity's search stages name the source rather than the agent, so they
 * light the agent and the source it reached through together.
 */
const STAGE_COMPONENTS: Record<string, ComponentId[]> = {
  emotional_boundary_preflight: ['preflight'],
  boundary_inference: ['librarian'],
  evidence_strength: ['librarian'],
  draft: ['muse'],
  revision: ['muse'],
  review: ['provenance'],
  search_rank_select: ['serendipity'],
  memory_search: ['serendipity', 'memory'],
  book_corpus_search: ['serendipity', 'librarian', 'corpus'],
  web_search: ['serendipity', 'web'],
  get_page: ['serendipity', 'web'],
  curation: ['sculptor'],
  curation_review: ['curation_review'],
  surfacing: ['sculptor'],
}

/** Fallback for a stage the allowlist collapsed to "processing". */
const AGENT_COMPONENTS: Record<string, ComponentId[]> = {
  Muse: ['muse'],
  Provenance: ['provenance'],
  Librarian: ['librarian'],
  Serendipity: ['serendipity'],
  Sculptor: ['sculptor'],
  Exa: ['web'],
  Application: ['release'],
}

function componentsFor(event: ProgressEvent): ComponentId[] {
  return STAGE_COMPONENTS[event.stage] ?? AGENT_COMPONENTS[event.agent] ?? []
}

// Coordinates follow the explorer's 1200-wide authoring space so the shared
// layout places these nodes in the same regions as the curated Scenes.
const SPINE: GraphNode[] = [
  { id: 'input', x: 100, y: 370 },
  { id: 'preflight', x: 275, y: 370 },
  { id: 'muse', x: 455, y: 370 },
  { id: 'provenance', x: 740, y: 370 },
  { id: 'release', x: 940, y: 370 },
  { id: 'response', x: 1110, y: 370 },
]

const SOURCE_POSITIONS: Partial<Record<ComponentId, GraphNode>> = {
  corpus: { id: 'corpus', x: 235, y: 145 },
  librarian: { id: 'librarian', x: 455, y: 145 },
  serendipity: { id: 'serendipity', x: 680, y: 145 },
  web: { id: 'web', x: 940, y: 145 },
  memory: { id: 'memory', x: 90, y: 145 },
  sculptor: { id: 'sculptor', x: 685, y: 145 },
  curation_review: { id: 'curation_review', x: 900, y: 145 },
}

function edge(
  source: ComponentId, target: ComponentId, label: string, summary: string,
  payload: string[], bidirectional = false,
): GraphEdge {
  return { id: `${source}-${target}`, source, target, label, summary, payload, bidirectional }
}

const SPINE_EDGES: GraphEdge[] = [
  edge('input', 'preflight', 'Line', 'The application ran the no-tool emotional preflight before Muse.', ['Your message']),
  edge('preflight', 'muse', 'Continue', 'A continue verdict let the application invoke Muse.', ['Continue disposition', 'Bounded Muse input']),
  edge('muse', 'provenance', 'Candidate', 'The complete draft and its declared evidence went to review.', ['Candidate wording', 'Evidence declarations', 'Memory nomination, if any']),
  edge('provenance', 'release', 'Review', 'Review does not release its own candidate.', ['Response verdict', 'Findings and trusted evidence']),
  edge('release', 'response', 'Released', 'Only wording that passed deterministic checks reached you.', ['Permitted reply', 'Release source']),
]

function optionalEdges(present: Set<ComponentId>): GraphEdge[] {
  const edges: GraphEdge[] = []
  if (present.has('librarian')) {
    edges.push(edge('muse', 'librarian', 'Evidence', 'Muse requested a permitted passage and Librarian returned exact source-backed evidence.', ['Retrieval query and safe ceiling', 'Exact text, version, and evidence IDs'], true))
  }
  if (present.has('corpus')) {
    edges.push(edge('librarian', 'corpus', '', 'Librarian read the authorized work and revision within the permitted scope.', ['Work ID and revision', 'Bounded corpus text'], true))
  }
  if (present.has('serendipity')) {
    edges.push(edge('muse', 'serendipity', 'Explore', 'Muse requested a bounded connection; application grants constrained every search.', ['Cue and intent', 'Allowed sources and ceilings', 'Validated decision and selected evidence'], true))
    if (present.has('librarian')) {
      edges.push(edge('serendipity', 'librarian', '', 'Only permitted book evidence may enter the connection search.', ['Bounded query', 'Exact book evidence'], true))
    }
    if (present.has('web')) {
      edges.push(edge('serendipity', 'web', 'Permitted search', 'Guarded public discovery used generalized concepts; web-backed release still fails closed.', ['Non-private query', 'Opened pages and source URLs'], true))
    }
    if (present.has('memory')) {
      edges.push(edge('serendipity', 'memory', 'Memory search', 'Serendipity searched active account-scoped memories under application grants.', ['Bounded memory query', 'Eligible memory records'], true))
    }
  }
  if (present.has('sculptor')) {
    edges.push(edge('muse', 'sculptor', 'Memory work', 'Sculptor proposed curation or judged surfacing over bounded records.', ['Bounded authorized memories', 'Proposal, defer, or no change'], true))
  }
  if (present.has('curation_review')) {
    edges.push(edge('sculptor', 'curation_review', 'Proposal', 'A separate no-tool review bound its verdict to one exact curation proposal.', ['Curation proposal digest', 'Bound pass, revise, or reject'], true))
  }
  return edges
}

function collectActivity(events: ProgressEvent[]) {
  const activity = new Map<ComponentId, ComponentActivity>()
  for (const event of events) {
    for (const id of componentsFor(event)) {
      const existing = activity.get(id) ?? { id, status: 'running' as ActivityStatus, stages: [] }
      const stage = existing.stages.find((item) => item.stage === event.stage)
      if (stage) {
        stage.status = event.status
        stage.elapsedMs = event.elapsed_ms
      } else {
        existing.stages.push({ stage: event.stage, status: event.status, elapsedMs: event.elapsed_ms })
      }
      // A component is only settled once none of its stages are still running,
      // and any failure or decline outranks a completed sibling stage.
      existing.status = existing.stages.some((item) => item.status === 'running')
        ? 'running'
        : existing.stages.some((item) => item.status === 'failed')
          ? 'failed'
          : existing.stages.some((item) => item.status === 'declined')
            ? 'declined'
            : 'complete'
      activity.set(id, existing)
    }
  }
  return activity
}

function observedSteps(events: ProgressEvent[], userMessage: string): [WalkthroughStep, ...WalkthroughStep[]] {
  const steps: WalkthroughStep[] = [{
    title: 'Your message enters the turn',
    description: `The application opened a turn for "${userMessage}" and supplied account identity, source grants, and policy. The text carries meaning only — never permissions.`,
    nodes: ['input', 'preflight'],
    edges: ['input-preflight'],
  }]

  for (const event of events) {
    if (event.status === 'running') continue
    const nodes = componentsFor(event)
    if (!nodes.length) continue
    const label = formatMachineLabel(event.stage)
    steps.push({
      title: `${event.agent} · ${label}`,
      description: `${event.detail} Reported at ${(event.elapsed_ms / 1000).toFixed(1)}s, handed from ${event.input_origin} to ${event.output_receiver}.`,
      nodes,
      edges: [],
    })
  }

  steps.push({
    title: 'The application released the reply',
    description: 'Deterministic checks resolved every declaration after review. Only permitted wording entered the conversation, and a withheld candidate suppresses any save notice.',
    nodes: ['release', 'response'],
    edges: ['release-response'],
  })
  return steps as [WalkthroughStep, ...WalkthroughStep[]]
}

/**
 * Build a map of one real chat turn from its content-free progress stream.
 *
 * The spine is always shown because every turn runs it; retrieval, connection,
 * and memory components appear only when the turn actually reached them.
 */
export function buildLiveTurn(options: {
  events: ProgressEvent[]
  userMessage: string
  turn?: TurnRecord
}): LiveTurn {
  const { events, userMessage, turn } = options
  const activity = collectActivity(events)
  const present = new Set<ComponentId>(activity.keys())

  const extras = [...present]
    .filter((id): id is keyof typeof SOURCE_POSITIONS & ComponentId => id in SOURCE_POSITIONS)
    .map((id) => SOURCE_POSITIONS[id])
    .filter((node): node is GraphNode => node !== undefined)

  const nodes = [...SPINE, ...extras].map((node) => {
    const seen = activity.get(node.id)
    if (!seen) return node
    const last = seen.stages[seen.stages.length - 1]
    const elapsed = last ? `${(last.elapsedMs / 1000).toFixed(1)}s` : undefined
    return {
      ...node,
      footer: {
        left: elapsed,
        right: seen.status === 'complete' ? 'done' : seen.status,
        tone: seen.status === 'failed' ? 'bad' as const
          : seen.status === 'running' ? 'neutral' as const
            : 'good' as const,
      },
    }
  })
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges = [...SPINE_EDGES, ...optionalEdges(present)]
    .filter((item) => nodeIds.has(item.source) && nodeIds.has(item.target))

  const running = [...activity.values()].filter((item) => item.status === 'running')
  const release = turn?.inspection.release

  const scene: Scene = {
    id: turn?.inspection.muse_turn.turn_id ?? 'in-flight',
    title: userMessage || 'Current turn',
    summary: running.length
      ? `Running now: ${running.map((item) => item.id.replaceAll('_', ' ')).join(', ')}.`
      : turn
        ? `Observed route for this turn. ${describeRelease(turn)}`
        : 'Waiting for the first stage of this turn.',
    status: 'implemented',
    statusNote: 'This map is one observed run, rebuilt from the server\'s content-free progress stream. Prompts, drafts, queries, and evidence never enter that stream.',
    input: { title: 'Your message', text: userMessage || '—' },
    expected: release
      ? [
        `Release source: ${formatMachineLabel(release.release_source)}.`,
        `Review path: ${release.provenance_verdicts.join(' → ') || 'unavailable'}.`,
        release.finding_codes.length
          ? `Findings raised: ${release.finding_codes.map(formatMachineLabel).join(', ')}.`
          : 'No review findings were raised.',
      ]
      : ['This turn has not produced a release decision yet.'],
    nodes,
    edges,
    steps: observedSteps(events, userMessage || 'your message'),
  }

  return {
    scene,
    activity: [...activity.values()],
    active: running.length
      ? { title: 'Running now', description: scene.summary, nodes: running.map((item) => item.id), edges: [] }
      : null,
    running: running.length > 0,
  }
}

function describeRelease(turn: TurnRecord): string {
  switch (turn.inspection.release?.release_source) {
    case 'application_clarification':
      return 'The application released a validated clarification question.'
    case 'application_safe_decline':
      return 'The candidate was withheld and the application released a safe decline.'
    case 'application_emotional_boundary':
      return 'The application released its fixed emotional boundary response.'
    default:
      return 'Provenance approved the Muse candidate and deterministic checks released it.'
  }
}
