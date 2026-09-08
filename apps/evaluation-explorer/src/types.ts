export type ComponentKind = 'agent' | 'service' | 'source' | 'output'

export type ComponentId =
  | 'input' | 'preflight' | 'muse' | 'provenance' | 'release' | 'response'
  | 'librarian' | 'corpus' | 'memory_policy' | 'memory' | 'sculptor'
  | 'serendipity' | 'web' | 'session' | 'capture_review' | 'curation_review' | 'proposal'

export interface ComponentDefinition {
  id: ComponentId
  label: string
  role: string
  kind: ComponentKind
  summary: string
  receives: string[]
  returns: string[]
  authority: string
}

export interface GraphNode {
  id: ComponentId
  x: number
  y: number
  label?: string
  role?: string
}

export interface GraphEdge {
  id: string
  source: ComponentId
  target: ComponentId
  label: string
  summary: string
  payload: string[]
  bidirectional?: boolean
  emphasis?: boolean
}

export interface WalkthroughStep {
  title: string
  description: string
  nodes: ComponentId[]
  edges: string[]
}

export interface Scene {
  id: string
  title: string
  summary: string
  status: 'implemented' | 'target' | 'component'
  statusNote: string
  input: { title: string; text: string }
  expected: string[]
  nodes: GraphNode[]
  edges: GraphEdge[]
  steps: [WalkthroughStep, ...WalkthroughStep[]]
}

export interface ObjectiveScenes {
  objectiveId: string
  scenes: [Scene, ...Scene[]]
}

export type InspectorSelection =
  | { kind: 'node'; id: ComponentId }
  | { kind: 'edge'; id: string }
  | { kind: 'scene' }
  | { kind: 'criteria' }
  | { kind: 'about' }
  | { kind: 'history' }
