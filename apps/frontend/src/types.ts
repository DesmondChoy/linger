export type Connection = {
  status: 'proposal'
  tentative_claim: string
  evidence_ids: string[]
  interpretation: string
  uncertainty: 'low' | 'medium' | 'high'
  suggested_follow_up: string
  cultural_suggestion?: {
    kind: 'song'
    title: string
    creator: string
    source_url: string
    rationale: string
  } | null
}

export type ConnectionBrief = {
  cue: string
  book_id: string | null
  chapter_max: number | null
  intent: 'find_connection' | 'get_recommendation'
  allowed_sources: string[]
}

export type AgentTrace = {
  agent: 'Router' | 'Muse' | 'Librarian' | 'Serendipity' | 'Provenance' | 'Memory & Policy'
  status: 'waiting' | 'running' | 'complete' | 'declined' | 'skipped' | 'not_wired' | 'failed'
  detail: string
}

export type MuseTurnContract = {
  turn_id: string
  user_message: string
  reading_context: { work_id: string; chapter_max: number; boundary_source: 'reader_confirmed' } | null
  policy: {
    spoiler_ceiling: number | null
    allow_retrieval: boolean
    allow_connection: boolean
    allow_memory_capture: boolean
  }
}

export type ContextResolution = {
  status: 'confirmed' | 'inferred' | 'unknown'
  work_id: string | null
  work_title: string | null
  chapter_max: number | null
  boundary_source: 'reader_confirmed' | 'inferred_from_question' | null
  explanation: string
}

export type PromptInspection = {
  dynamic_input: string
}

export type LibrarianRequest = {
  query: string
  book_scopes: { book_id: string; chapter_max: number }[]
  purpose: 'connection_discovery'
}

export type EvidenceBundle = {
  items: {
    evidence_id: string
    source_title: string
    location: string
    chapter: number | null
    excerpt: string
    relevance: number
    source_kind: 'book_corpus'
  }[]
  retrieval_note: string
}

export type RiskCode =
  | 'unresolved_evidence'
  | 'misattribution'
  | 'spoiler'
  | 'boundary_violation'
  | 'uncited_web_claim'
  | 'unsupported_claim'
  | 'sensitive_content'
  | 'prompt_injection'

export type CaptureInspection = {
  nomination: 'candidate' | 'no_candidate' | 'unavailable'
  provenance_decision: 'allow_capture' | 'reject_capture' | 'no_candidate' | null
  binding: 'exact' | 'not_applicable' | 'invalid'
  storage: 'committed' | 'refused' | 'not_applicable'
  reason_code: string | null
}

export type ReleaseInspection = {
  release_source: 'muse_candidate' | 'application_safe_decline'
  provenance_verdicts: ('pass' | 'revise' | 'reject')[]
  finding_codes: RiskCode[]
  revision_count: number
  failure_stage: 'muse_draft' | 'provenance_review' | 'muse_revision' | 'deterministic_validation' | null
  capture: CaptureInspection
}

export type TurnTimeline = {
  id: string
  userInput: string
  response: string
  traces: AgentTrace[]
  contract?: MuseTurnContract
  contextResolution?: ContextResolution
  promptInspection?: PromptInspection
  connectionBrief?: ConnectionBrief
  librarianRequest?: LibrarianRequest
  evidenceBundle?: EvidenceBundle
  connection?: Connection
  release?: ReleaseInspection
  status: 'running' | 'complete' | 'failed'
}

export type TurnInspection = {
  muse_turn: MuseTurnContract
  context_resolution: ContextResolution
  traces: AgentTrace[]
  connection_brief: ConnectionBrief | null
  librarian_request: LibrarianRequest | null
  evidence_bundle: EvidenceBundle | null
  connection_proposal: Connection | null
  prompt: string
  release: ReleaseInspection | null
}

export type ChatResult = {
  reply: string
  inspection: TurnInspection
  memory_capture: MemoryCaptureNotice | null
}

export type MemoryCaptureNotice = {
  memory_id: string
  notice: 'Saved to your memories.'
}

export type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export type Memory = {
  memory_id: string
  text: string
  capture_type: 'explicit' | 'automatic' | 'correction'
  evidence_ids: string[]
  created_at: string
  updated_at: string
}

export type MemoryState = {
  capture_enabled: boolean
  memories: Memory[]
}

export type MemorySaveResult = {
  memory: Memory
  created: boolean
}
