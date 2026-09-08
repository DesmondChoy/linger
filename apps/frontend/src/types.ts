export type ConnectionDecline = {
  reason:
    | 'no_permitted_evidence'
    | 'insufficient_evidence'
    | 'unsupported_cue'
    | 'generic_theme_match'
    | 'no_clear_winner'
    | 'spoiler_boundary'
    | 'source_scope_violation'
    | 'unsafe_evidence'
    | 'retrieval_unavailable'
  failure_code: 'connection_discovery_failed' | null
}

export type AgentTrace = {
  agent: 'Router' | 'Muse' | 'Librarian' | 'Serendipity' | 'Provenance' | 'Memory & Policy'
  status: 'complete' | 'declined' | 'skipped' | 'not_run' | 'failed'
  detail: string
}

export type MuseTurnContract = {
  turn_id: string
  user_message: string
  reading_context: {
    work_id: string
    chapter_max: number
    boundary_source: 'reader_confirmed' | 'librarian_inferred'
  } | null
  policy: {
    spoiler_ceiling: number | null
    allow_retrieval: boolean
    allow_connection: boolean
    allow_memory_capture: boolean
    emotional_content: {
      version: '2'
      boundary_response_id: 'distressing_disclosure_v1'
      prohibit_diagnosis: true
      stop_probing_after_distress: true
      suppress_tools_after_distress: true
      suppress_capture_after_distress: true
    }
  }
}

export type ContextResolution = {
  status: 'confirmed' | 'inferred' | 'unknown'
  work_id: string | null
  work_title: string | null
  book_version_id: string | null
  chapter_max: number | null
  boundary_source: 'reader_confirmed' | 'librarian_inferred' | null
  boundary_authorization_basis: 'explicit_progress' | 'memory_supported' | null
  boundary_confidence: number | null
  boundary_supporting_memory_ids: string[]
  boundary_supporting_locations: {
    evidence_id: string
    chapter_number: number
    location: string
  }[]
  clarification_question: string | null
  explanation: string
}

export type LibrarianGroundingCall = {
  request: Record<string, unknown>
  outcome: string
  response: Record<string, unknown>
}

export type RiskCode =
  | 'unresolved_evidence'
  | 'misattribution'
  | 'spoiler'
  | 'uncited_web_claim'
  | 'unsupported_claim'
  | 'sensitive_content'
  | 'emotional_policy_violation'
  | 'prompt_injection'

export type CaptureInspection = {
  nomination: 'candidate' | 'no_candidate' | 'unavailable'
  provenance_decision: 'allow_capture' | 'reject_capture' | 'no_candidate' | null
  binding: 'exact' | 'not_applicable' | 'invalid'
  storage: 'committed' | 'refused' | 'suppressed' | 'not_applicable'
  reason_code: string | null
}

export type ReleaseInspection = {
  release_source: 'muse_candidate' | 'application_clarification' | 'application_emotional_boundary' | 'application_safe_decline'
  boundary_origin: 'preflight' | 'candidate_review' | null
  provenance_verdicts: ('pass' | 'revise' | 'reject')[]
  finding_codes: RiskCode[]
  released_evidence_ids: string[]
  revision_count: number
  failure_stage: 'emotional_boundary_preflight' | 'muse_draft' | 'provenance_review' | 'muse_revision' | 'deterministic_validation' | null
  failure_type: 'application' | 'model' | 'validation' | null
  failure_retryable: boolean | null
  capture: CaptureInspection
}

export type TraceReference = {
  trace_id: string
}

export type TurnInspection = {
  muse_turn: MuseTurnContract
  context_resolution: ContextResolution
  traces: AgentTrace[]
  connection_decline: ConnectionDecline | null
  librarian_grounding: LibrarianGroundingCall[]
  prompt: string
  release: ReleaseInspection | null
}

export type ChatResult = {
  reply: string
  inspection: TurnInspection
  trace: TraceReference
  memory_capture: MemoryCaptureNotice | null
}

export type MemoryCaptureNotice = {
  notice: 'Saved to your memories.'
}

export type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
}
