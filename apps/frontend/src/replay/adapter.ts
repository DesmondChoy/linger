import type {
  AgentExchange,
  AgentName,
  AgentTrace,
  CaptureInspection,
  ContextResolution,
  LibrarianGroundingCall,
  Message,
  MuseTurnContract,
  ProgressEvent,
  ReleaseInspection,
  TurnRecord,
} from '../types'
import type { Persona, PersonaRun, PlannedScene, RecordedExchange, RecordedScene, RecordedTurn } from './types'

/** Shown wherever a recorded run kept no value, so nothing is invented to fill the gap. */
export const NOT_RECORDED = 'Not recorded in this run.'

const AGENTS = new Set<AgentName>(['Application', 'Muse', 'Provenance', 'Librarian', 'Serendipity', 'Sculptor', 'Exa'])
const TRACED = new Set(['Muse', 'Librarian', 'Serendipity', 'Provenance'])
const RELEASES = new Set([
  'muse_candidate', 'application_clarification', 'application_emotional_boundary',
  'application_language_boundary', 'application_safe_decline',
])

function agent(value: string | null): AgentName {
  return value && AGENTS.has(value as AgentName) ? value as AgentName : 'Application'
}

function stageStatus(status: string): ProgressEvent['status'] {
  if (status === 'success') return 'complete'
  if (status === 'decline' || status === 'declined') return 'declined'
  return 'failed'
}

/** Rebuild the progress stream the live map reads from the recorded agent runs. */
export function progressFrom(exchanges: RecordedExchange[]): ProgressEvent[] {
  const events: ProgressEvent[] = []
  for (const exchange of exchanges) {
    const base = {
      agent: agent(exchange.role),
      stage: exchange.stage ?? 'processing',
      input_origin: agent(exchange.inputOrigin),
      output_receiver: agent(exchange.outputReceiver),
    }
    events.push({ ...base, sequence: events.length + 1, elapsed_ms: exchange.startMs ?? 0, status: 'running', detail: `${base.agent} started ${base.stage}.` })
    events.push({
      ...base,
      sequence: events.length + 1,
      elapsed_ms: exchange.endMs ?? exchange.startMs ?? 0,
      status: stageStatus(exchange.status),
      detail: exchange.failureCode ? `${base.agent} ${base.stage}: ${exchange.failureCode}.` : `${base.agent} finished ${base.stage}.`,
    })
  }
  return events
}

function devExchanges(exchanges: RecordedExchange[]): AgentExchange[] {
  return exchanges.map((exchange) => ({
    role: exchange.role ?? 'Application',
    stage: exchange.stage ?? 'processing',
    skill: exchange.skill,
    input_prompt: exchange.input ?? NOT_RECORDED,
    status: exchange.status,
    failure_code: exchange.failureCode,
    steps: exchange.toolCalls.map((call) => ({ kind: 'tool-call', tool: call.tool ?? undefined, content: call.outcome })),
    output: exchange.output ?? null,
  }))
}

function traces(exchanges: RecordedExchange[]): AgentTrace[] {
  return exchanges
    .filter((exchange) => exchange.role && TRACED.has(exchange.role))
    .map((exchange) => ({
      agent: exchange.role as AgentTrace['agent'],
      status: exchange.status === 'success' ? 'complete' : 'failed',
      detail: `${exchange.stage ?? 'processing'}${exchange.failureCode ? ` · ${exchange.failureCode}` : ''}`,
    }))
}

const UNKNOWN_CONTEXT: ContextResolution = {
  status: 'unknown', work_id: null, work_title: null, book_version_id: null, chapter_max: null,
  part_id: 'main', unit_ids: [], boundary_source: null, boundary_authorization_basis: null,
  boundary_confidence: null, boundary_supporting_memory_ids: [], boundary_supporting_locations: [],
  clarification_question: null, explanation: NOT_RECORDED,
}

const NO_CAPTURE: CaptureInspection = {
  nomination: 'unavailable', provenance_decision: null, binding: 'not_applicable',
  storage: 'not_applicable', reason_code: null,
}

function release(turn: RecordedTurn): ReleaseInspection | null {
  if (!turn.releaseSource || !RELEASES.has(turn.releaseSource)) return null
  return {
    release_source: turn.releaseSource as ReleaseInspection['release_source'],
    boundary_origin: null,
    provenance_verdicts: turn.provenanceVerdicts as ReleaseInspection['provenance_verdicts'],
    finding_codes: [],
    released_evidence_ids: turn.releasedEvidenceIds,
    revision_count: Math.max(0, turn.provenanceVerdicts.length - 1),
    failure_stage: null,
    failure_type: null,
    failure_retryable: null,
    capture: (turn.capture as CaptureInspection | null) ?? NO_CAPTURE,
  }
}

/** A recorded Librarian lookup in the shape Inspect lists grounding calls. */
function groundingCall(call: Record<string, unknown>): LibrarianGroundingCall {
  const { call_outcome: outcome, evidence, clarification_question: question, failure_code: failure, ...request } = call
  return {
    request,
    outcome: String(outcome ?? call.retrieval_outcome ?? 'unknown'),
    response: { evidence, clarification_question: question, failure_code: failure },
  }
}

function record(options: {
  id: string
  sessionId: string
  userMessage: string
  reply: string
  turn: RecordedTurn
  grading?: TurnRecord['grading']
}): TurnRecord {
  const { id, sessionId, userMessage, reply, turn, grading } = options
  const context = (turn.contextResolution as ContextResolution | null) ?? UNKNOWN_CONTEXT
  const reading = context.status === 'confirmed' && context.work_id && context.boundary_source
    ? { work_id: context.work_id, chapter_max: context.chapter_max, part_id: context.part_id, unit_ids: context.unit_ids, boundary_source: context.boundary_source }
    : null
  // Muse's own recorded contract, when it drafted; otherwise a shell whose policy is never shown.
  const museTurn = turn.museTurn
    ? { ...(turn.museTurn as MuseTurnContract), turn_id: id, user_message: userMessage }
    : null
  return {
    reply,
    trace: { trace_id: '0'.repeat(32) },
    memory_capture: turn.capturedMemory ? { notice: 'Saved to your memories.' } : null,
    sources: turn.sources,
    progress: progressFrom(turn.exchanges),
    sessionId,
    grading,
    replayed: { museTurnRecorded: museTurn !== null },
    inspection: {
      muse_turn: museTurn ?? {
        turn_id: id,
        user_message: userMessage,
        reading_context: reading,
        policy: {
          spoiler_ceiling: reading?.chapter_max ?? null,
          allow_retrieval: reading !== null,
          allow_connection: false,
          allow_memory_capture: false,
          emotional_content: {
            version: '3', boundary_response_id: 'distressing_disclosure_v1',
            self_harm_response_id: 'self_harm_disclosure_v1', prohibit_diagnosis: true,
            stop_probing_after_distress: true, suppress_tools_after_distress: true,
            suppress_capture_after_distress: true,
          },
        },
      },
      context_resolution: context,
      traces: traces(turn.exchanges),
      connection_decline: null,
      librarian_grounding: turn.groundingCalls.map(groundingCall),
      memory: turn.capturedMemory?.memoryId
        ? {
          active_count: 0,
          captured_memory_id: turn.capturedMemory.memoryId,
          cited_memory_ids: [],
          texts: { [turn.capturedMemory.memoryId]: turn.capturedMemory.text },
        }
        : null,
      dev_trace: { agent_exchanges: devExchanges(turn.exchanges), connection_events: turn.connectionEvents },
      prompt: turn.prompt ?? NOT_RECORDED,
      release: release(turn),
    },
  }
}

function curationPrompt(scene: PlannedScene, persona: Persona, recorded: { id: string; text: string }[]): string {
  // The memories Sculptor actually received, falling back to the Scene's planned Props.
  const props = recorded.length ? recorded : persona.props.filter((prop) => scene.propIds.includes(prop.id))
  const listed = props.map((prop) => `• ${prop.text}`).join('\n')
  return `Offline curation task (no reader message). Sculptor was given ${props.length} saved ${props.length === 1 ? 'memory' : 'memories'}:\n${listed}`
}

function curationReply(response: Record<string, unknown> | null): string {
  if (!response) return NOT_RECORDED
  if (response.kind === 'no_curation_proposal') return `No change proposed. ${String(response.reason ?? '')}`.trim()
  const action = (response.action ?? {}) as Record<string, unknown>
  const sources = Array.isArray(action.source_memory_ids) ? action.source_memory_ids.join(', ') : 'unknown sources'
  const detail = action.summary ? `\n\nSummary: ${String(action.summary)}` : action.topic_label ? `\n\nTopic: ${String(action.topic_label)}` : ''
  return `Proposed ${String(action.action ?? 'an action').replaceAll('_', ' ')} over ${sources}.${detail}`
}

function grading(scene: RecordedScene, planned: PlannedScene | undefined): TurnRecord['grading'] {
  return {
    sceneId: scene.sceneId,
    status: scene.status,
    offline: scene.curation !== null,
    expected: planned?.expected ?? [],
    prohibited: planned?.prohibited ?? [],
    failures: scene.failures,
    executionFailures: scene.executionFailures,
    assessment: scene.assessment,
    analysis: scene.analysis,
  }
}

export type Replay = { messages: Message[]; timeline: TurnRecord[] }

/**
 * Turn one recorded run into the chat feed and turn records the live UI renders.
 *
 * Each Scene opens its own labelled conversation; its answer key rides on the
 * Scene's last turn so the turn summary can show it beside what was recorded.
 */
export function replayRun(persona: Persona, run: PersonaRun): Replay {
  const planned = new Map(persona.scenes.map((scene) => [scene.id, scene]))
  const ordered = [...run.scenes].sort((a, b) => (planned.get(a.sceneId)?.order ?? 0) - (planned.get(b.sceneId)?.order ?? 0))
  const messages: Message[] = []
  const timeline: TurnRecord[] = []
  ordered.forEach((scene, sceneIndex) => {
    const plan = planned.get(scene.sceneId)
    const sessionId = `${run.id}:${scene.sceneId}`
    const label = `Scene ${sceneIndex + 1} · ${scene.sceneId} · ${scene.status}`
    const turns: { userMessage: string; reply: string; turn: RecordedTurn }[] = scene.curation && plan
      ? [{
        userMessage: curationPrompt(plan, persona, scene.curation.inputMemories),
        reply: curationReply(scene.curation.response),
        turn: {
          userMessage: '', reply: '', releaseSource: null, provenanceVerdicts: [], capture: null,
          contextResolution: null, museTurn: null, prompt: null, memorySurfacing: null, releasedEvidenceIds: [],
          sources: [], groundingCalls: [], connectionEvents: [], capturedMemory: null, exchanges: scene.curation.exchanges,
        },
      }]
      : scene.turns.map((turn) => ({ userMessage: turn.userMessage, reply: turn.reply || NOT_RECORDED, turn }))
    turns.forEach((item, turnIndex) => {
      const id = `${sessionId}:${turnIndex}`
      messages.push(
        { id, role: 'user', content: item.userMessage, sessionId, dividerLabel: turnIndex === 0 ? label : undefined },
        { id: `${id}-assistant`, role: 'assistant', content: item.reply, sessionId, sources: item.turn.sources },
      )
      timeline.push(record({
        id, sessionId, userMessage: item.userMessage, reply: item.reply, turn: item.turn,
        grading: turnIndex === turns.length - 1 ? grading(scene, plan) : undefined,
      }))
    })
  })
  return { messages, timeline }
}
