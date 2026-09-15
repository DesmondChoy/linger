import data from './evaluations.json'

export interface EvaluationGrade {
  objectiveId: string | null
  hardPass: boolean
  failures: string[]
}

export interface EvaluationObservation {
  role: string | null
  stage: string | null
  status: string | null
  toolCalls: number | null
  template: string | null
  templateVersion: string | null
}

/** One scene as a single run actually performed it. */
export interface EvaluationRunScene {
  sceneId: string | null
  routeCalled: boolean
  routedCeiling: number | null
  boundaryDecision: string | null
  boundarySupportMemoryIds: string[]
  groundingCallCount: number
  releasedEvidenceIds: string[]
  releaseSource: string | null
  provenanceVerdicts: string[]
  reply: string
  observations: EvaluationObservation[]
  grades: EvaluationGrade[]
}

/**
 * One build of Linger answering a scenario.
 *
 * Runs of the same scenario usually differ by `systemVariant`, so a set of them
 * is a record of the system changing rather than repeated trials of one build.
 */
export interface EvaluationRun {
  id: string
  label: string
  file: string
  systemVariant: string | null
  gitHead: string | null
  model: string | null
  groundTruthStatus: string | null
  passed: number | null
  total: number | null
  cautions: string[]
  scenes: EvaluationRunScene[]
}

export interface EvaluationScene {
  id: string
  order: number | null
  freshSession: boolean
  objectiveIds: string[]
  propIds: string[]
  line: string
  expected: string[]
  prohibited: string[]
}

export interface EvaluationProp {
  id: string | null
  sourceText: string
  activeScenes: (string | null)[]
}

export interface EvaluationScenario {
  id: string
  objectiveIds: string[]
  persona: { id: string | null; context: string }
  props: EvaluationProp[]
  scenes: EvaluationScene[]
  runs: EvaluationRun[]
  adoptionRecorded: boolean
}

export const evaluations = data as { source: string; scenarios: EvaluationScenario[] }

/** Only scenarios with at least one recorded run can be shown as evidence. */
export const playableScenarios = evaluations.scenarios.filter((item) => item.runs.length > 0)
