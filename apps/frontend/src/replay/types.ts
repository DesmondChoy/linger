/** Shape of `personas/*.json`, written by `apps/frontend/scripts/export_personas.py`. */

export type RecordedExchange = {
  sequence: number | null
  role: string | null
  stage: string | null
  skill: string | null
  status: string
  failureCode: string | null
  inputOrigin: string | null
  outputReceiver: string | null
  startMs: number | null
  endMs: number | null
  /** The synthetic input this agent received, clipped. */
  input: string | null
  output: string | null
  toolCalls: { tool: string | null; outcome: string | null }[]
}

export type RecordedTurn = {
  userMessage: string
  reply: string
  releaseSource: string | null
  provenanceVerdicts: string[]
  capture: Record<string, unknown> | null
  contextResolution: Record<string, unknown> | null
  /** Muse's recorded MuseTurn contract, from its draft input; null when Muse never drafted. */
  museTurn: Record<string, unknown> | null
  /** Muse's full assembled draft input, as recorded. */
  prompt: string | null
  memorySurfacing: unknown
  releasedEvidenceIds: string[]
  sources: { kind: 'book' | 'web' | 'memory'; label: string; location: string | null; url: string | null }[]
  groundingCalls: Record<string, unknown>[]
  connectionEvents: Record<string, unknown>[]
  capturedMemory: { memoryId: string | null; text: string } | null
  exchanges: RecordedExchange[]
}

export type RecordedCuration = {
  inputMemories: { id: string; text: string }[]
  response: Record<string, unknown> | null
  outcome: unknown
  status: string | null
  sourcesUnchanged: boolean | null
  exchanges: RecordedExchange[]
}

export type RecordedScene = {
  sceneId: string
  status: 'passed' | 'failed' | 'ungraded'
  failures: string[]
  executionFailures: string[]
  assessment: string | null
  analysis: string | null
  turns: RecordedTurn[]
  curation: RecordedCuration | null
}

export type PersonaRun = {
  id: string
  startedAt: string | null
  model: string | null
  systemVariant: string | null
  passed: number
  failed: number
  ungraded: number
  total: number
  executionFailures: number
  logfireUrl: string | null
  verdict: string | null
  scenes: RecordedScene[]
}

export type PlannedScene = {
  id: string
  order: number | null
  freshSession: boolean
  objectiveIds: string[]
  propIds: string[]
  lines: string[]
  expected: string[]
  prohibited: string[]
}

export type Persona = {
  id: string
  title: string
  dated: string
  description: string
  family: string
  objectiveIds: string[]
  personId: string | null
  context: string
  props: { id: string; text: string }[]
  scenes: PlannedScene[]
  runs: PersonaRun[]
}

/** One gallery card, from `personas/index.json`; the full persona loads on open. */
export type PersonaSummary = Pick<Persona, 'id' | 'title' | 'dated' | 'description' | 'family'> & {
  runs: Pick<PersonaRun, 'id' | 'startedAt' | 'passed' | 'failed' | 'ungraded' | 'total' | 'executionFailures'>[]
}

export type PersonaIndex = {
  source: string
  families: { id: string; label: string }[]
  personas: PersonaSummary[]
}
