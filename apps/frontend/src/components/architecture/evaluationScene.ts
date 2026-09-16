import type {
  ComponentId,
  EvaluationRun,
  EvaluationRunScene,
  EvaluationScene,
  GraphEdge,
  GraphNode,
  Scene,
  WalkthroughStep,
} from '@linger/architecture-map'

/**
 * Failure codes that tell us what the adopted key required.
 *
 * A component the run never reached is only drawn when the key demanded it, and
 * the only trustworthy evidence of that demand is a recorded grade failure. We
 * never infer a requirement the archive does not state.
 */
const RETRIEVAL_REQUIRED = [
  'required_grounding_evidence_not_retrieved',
  'grounded_response_released_no_evidence',
  'exact_quotation_missing_or_unreleased',
]
const MEMORY_REQUIRED = [
  'boundary_memory_support_differs_from_authorised_props',
  'boundary_support_differs_from_ground_truth',
  'inferred_scope_differs_from_ground_truth',
]

function failures(scene: EvaluationRunScene): string[] {
  return scene.grades.flatMap((grade) => grade.failures)
}

function demanded(codes: string[], prefixes: string[]): boolean {
  return codes.some((code) => prefixes.some((prefix) => code.startsWith(prefix)))
}

function observation(scene: EvaluationRunScene, role: string, stage: string) {
  return scene.observations.find((item) => item.role === role && item.stage === stage)
}

const SPINE: Record<string, { x: number; y: number }> = {
  input: { x: 100, y: 370 },
  preflight: { x: 275, y: 370 },
  muse: { x: 455, y: 370 },
  provenance: { x: 740, y: 370 },
  release: { x: 940, y: 370 },
  response: { x: 1110, y: 370 },
}

const SOURCES: Record<string, { x: number; y: number }> = {
  memory: { x: 90, y: 145 },
  corpus: { x: 235, y: 145 },
  librarian: { x: 455, y: 145 },
}

function edge(
  source: ComponentId, target: ComponentId, label: string, summary: string,
  payload: string[], bidirectional = false,
): GraphEdge {
  return { id: `${source}-${target}`, source, target, label, summary, payload, bidirectional }
}

/**
 * What a recorded failure code means, in the words a reader needs.
 *
 * The archive grades per objective, not per outcome, so a code cannot be tied
 * to one sentence of the key. These are shown as the run's own findings rather
 * than as ticks beside the expected outcomes.
 */
const FAILURE_PROSE: Record<string, string> = {
  required_grounding_evidence_not_retrieved: 'Had to open the book. It never did.',
  grounded_response_released_no_evidence: 'Answered as if grounded, citing nothing.',
  exact_quotation_missing_or_unreleased: 'Had to quote exactly. No quotation appeared.',
  inferred_scope_differs_from_ground_truth: 'Settled on a different reading position than the key expects.',
  boundary_memory_support_differs_from_authorised_props: 'Used different memories than the key authorises for the boundary.',
  boundary_support_differs_from_ground_truth: 'Supported the reading boundary differently than the key expects.',
}

export function failureProse(code: string): string {
  const base = code.split(':')[0]
  return FAILURE_PROSE[base] ?? code.replaceAll('_', ' ')
}

export type EvaluationObjectiveResult = {
  objectiveId: string | null
  passed: boolean
  failures: string[]
}

export type EvaluationView = {
  scene: Scene
  /** Graded per objective, which is the granularity the archive records. */
  objectives: EvaluationObjectiveResult[]
  expected: string[]
  prohibited: string[]
  failureCodes: string[]
  /** True when the key wanted retrieval and the run never performed one. */
  retrievalMissing: boolean
  memoryMissing: boolean
}

/**
 * Build the annotated map for one recorded run of one scene.
 *
 * Components the run used are drawn with what they did; components the key
 * required but the run never reached are drawn muted, which is what makes a
 * failure legible as a broken chain rather than a score.
 */
export function buildEvaluationView(options: {
  run: EvaluationRun
  runScene: EvaluationRunScene
  scene: EvaluationScene
}): EvaluationView {
  const { run, runScene, scene } = options
  const codes = failures(runScene)

  const usedRetrieval = runScene.routeCalled
    || runScene.groundingCallCount > 0
    || runScene.releasedEvidenceIds.length > 0
  const usedMemory = runScene.boundarySupportMemoryIds.length > 0
  const retrievalMissing = !usedRetrieval && demanded(codes, RETRIEVAL_REQUIRED)
  const memoryMissing = !usedMemory && demanded(codes, MEMORY_REQUIRED)

  const nodes: GraphNode[] = []
  const quotationMissing = codes.some((code) => code.startsWith('exact_quotation_missing_or_unreleased'))

  if (usedMemory || memoryMissing) {
    nodes.push({
      ...SOURCES.memory, id: 'memory', label: 'Her memory', role: 'Seeded before the run',
      muted: !usedMemory,
      footer: usedMemory
        ? { left: `${runScene.boundarySupportMemoryIds.length} used`, right: 'consulted', tone: 'good' }
        : { right: 'never consulted', tone: 'bad' },
    })
  }
  if (usedRetrieval || retrievalMissing) {
    nodes.push({
      ...SOURCES.corpus, id: 'corpus', label: 'Book corpus', role: 'The book itself',
      muted: !usedRetrieval,
      footer: runScene.releasedEvidenceIds.length
        ? { left: `${runScene.releasedEvidenceIds.length} passage${runScene.releasedEvidenceIds.length === 1 ? '' : 's'}`, right: 'quoted', tone: 'good' }
        : { right: 'nothing quoted', tone: 'bad' },
    })
    nodes.push({
      ...SOURCES.librarian, id: 'librarian', role: 'Works out how far she read',
      muted: !usedRetrieval,
      footer: runScene.routeCalled
        ? { left: runScene.routedCeiling === null ? 'no ceiling' : `chapter ${runScene.routedCeiling}`, right: runScene.boundaryDecision ?? 'routed', tone: 'good' }
        : { right: 'never asked', tone: 'bad' },
    })
  }

  const preflight = observation(runScene, 'Provenance', 'emotional_boundary_preflight')
  const draft = observation(runScene, 'Muse', 'draft')
  const review = observation(runScene, 'Provenance', 'review')

  nodes.push({ ...SPINE.input, id: 'input', label: 'The message', role: 'Fixed for this scene', footer: { right: 'fixed' } })
  nodes.push({
    ...SPINE.preflight, id: 'preflight',
    footer: { left: `${preflight?.toolCalls ?? 0} tools`, right: preflight?.status === 'success' ? 'go on' : preflight?.status ?? 'not run', tone: 'good' },
  })
  nodes.push({
    ...SPINE.muse, id: 'muse', role: 'Writes the reply',
    footer: quotationMissing
      ? { left: `${draft?.toolCalls ?? 0} look-ups`, right: 'no quote', tone: 'bad' }
      : { left: `${draft?.toolCalls ?? 0} look-ups`, right: draft?.status ?? 'not run', tone: 'good' },
  })
  nodes.push({
    ...SPINE.provenance, id: 'provenance', role: 'Checks the draft',
    footer: { left: runScene.provenanceVerdicts.join(' → ') || '—', right: review?.status ?? 'not run', tone: 'good' },
  })
  nodes.push({
    ...SPINE.release, id: 'release', role: 'Final gate',
    footer: { left: `${runScene.releasedEvidenceIds.length} sources`, right: (runScene.releaseSource ?? '').replace('application_', '').replace('muse_', '') || 'released' },
  })
  nodes.push({ ...SPINE.response, id: 'response', role: 'Released wording', footer: { right: 'shown' } })

  const present = new Set(nodes.map((node) => node.id))
  const edges: GraphEdge[] = [
    edge('input', 'preflight', 'Line', 'The application checks the message before Muse sees it.', ['The message']),
    edge('preflight', 'muse', 'Continue', 'A continue verdict lets the application invoke Muse.', ['Continue disposition']),
    edge('muse', 'provenance', 'Candidate', 'The complete draft and its declared evidence go to review.', ['Candidate wording', 'Evidence declarations']),
    edge('provenance', 'release', 'Review', 'Review does not release its own candidate.', ['Response verdict', 'Findings']),
    edge('release', 'response', 'Released', 'Only checked wording reaches the reader.', ['Permitted reply']),
  ]
  if (present.has('librarian')) {
    edges.push(edge('muse', 'librarian', usedRetrieval ? 'Evidence' : 'Not asked', 'Muse asks for a permitted passage; Librarian returns exact source-backed evidence.', ['Retrieval query and safe ceiling', 'Exact text and evidence IDs'], true))
    edges.push(edge('librarian', 'corpus', '', 'Librarian reads the authorised work within the permitted scope.', ['Work and revision', 'Bounded corpus text'], true))
  }
  if (present.has('memory')) {
    edges.push(edge('memory', 'librarian', usedMemory ? 'Supports' : 'Unused', 'Durable records can support a reading-boundary inference.', ['Eligible memory records', 'Boundary support'], false))
  }

  const objectives: EvaluationObjectiveResult[] = runScene.grades.map((grade) => ({
    objectiveId: grade.objectiveId,
    passed: grade.hardPass,
    failures: grade.failures,
  }))

  const steps: [WalkthroughStep, ...WalkthroughStep[]] = [{
    title: 'What this run did',
    description: runScene.reply ? runScene.reply.slice(0, 220) : 'No reply was recorded for this scene.',
    nodes: [...present],
    edges: [],
  }]

  return {
    scene: {
      id: `${run.id}:${scene.id}`,
      title: scene.id,
      summary: retrievalMissing
        ? 'The adopted key required a look-up. This build never made one.'
        : 'The route this build actually took.',
      status: 'implemented',
      statusNote: `Recorded run ${run.id.slice(0, 8)}, build ${run.systemVariant ?? 'unknown'}.`,
      input: { title: 'Scene line', text: scene.line },
      expected: scene.expected,
      nodes,
      edges: edges.filter((item) => present.has(item.source) && present.has(item.target)),
      steps,
    },
    objectives,
    expected: scene.expected,
    prohibited: scene.prohibited,
    failureCodes: [...new Set(codes)],
    retrievalMissing,
    memoryMissing,
  }
}
