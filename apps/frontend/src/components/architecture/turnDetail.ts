import { components } from '@linger/architecture-map'
import type { ComponentId, GraphEdge, Scene } from '@linger/architecture-map'
import type { TurnRecord } from '../../types'

export type DetailRecord = {
  label: string
  /** Rendered as JSON. This is the turn's own data, never a description of it. */
  value: unknown
}

export type ComponentDetail = {
  title: string
  role: string
  /** One plain sentence about what happened here, this turn. */
  did: string
  records: DetailRecord[]
  /** The standing contract, shown under the run data rather than instead of it. */
  receives: string[]
  returns: string[]
  authority: string
}

function agentTrace(turn: TurnRecord, agent: string) {
  return turn.inspection.traces.find((trace) => trace.agent === agent)
}

/**
 * What one component actually did on one turn.
 *
 * Every record here is lifted from the turn's own inspection payload — the
 * MuseTurn contract, the resolved context, the grounding calls, the release
 * decision. The registry text describing what a component *is* comes last.
 */
export function componentDetail(id: ComponentId, turn: TurnRecord): ComponentDetail {
  const definition = components[id]
  const inspection = turn.inspection
  const release = inspection.release
  const base = {
    title: definition.label,
    role: definition.role,
    receives: definition.receives,
    returns: definition.returns,
    authority: definition.authority,
  }

  switch (id) {
    case 'input':
      return {
        ...base,
        did: 'The application opened a turn for this message and attached the trusted request context.',
        records: [
          { label: 'Message and turn identity', value: { turn_id: inspection.muse_turn.turn_id, user_message: inspection.muse_turn.user_message } },
          { label: 'Trace', value: turn.trace },
        ],
      }
    case 'preflight':
      return {
        ...base,
        did: release?.boundary_origin === 'preflight'
          ? 'The no-tool preflight found distress and required the fixed emotional boundary.'
          : 'The no-tool preflight allowed ordinary reflection to continue.',
        records: [{ label: 'Emotional content policy in force', value: inspection.muse_turn.policy.emotional_content }],
      }
    case 'muse':
      return {
        ...base,
        did: agentTrace(turn, 'Muse')?.detail ?? 'Muse drafted the candidate reply.',
        records: [
          { label: 'MuseTurn contract', value: inspection.muse_turn },
          { label: 'Assembled dynamic input', value: inspection.prompt },
        ],
      }
    case 'librarian':
      return {
        ...base,
        did: inspection.librarian_grounding.length
          ? `Librarian answered ${inspection.librarian_grounding.length} grounding call${inspection.librarian_grounding.length === 1 ? '' : 's'} within the permitted ceiling.`
          : 'Librarian resolved the reading context for this turn.',
        records: [
          { label: 'Context resolution', value: inspection.context_resolution },
          ...(inspection.librarian_grounding.length
            ? [{ label: 'Grounding calls', value: inspection.librarian_grounding }]
            : []),
        ],
      }
    case 'corpus':
      return {
        ...base,
        did: release?.released_evidence_ids.length
          ? `${release.released_evidence_ids.length} passage${release.released_evidence_ids.length === 1 ? '' : 's'} entered the released reply.`
          : 'No corpus passage entered the released reply.',
        records: [{
          label: 'Permitted scope and released evidence',
          value: {
            work_id: inspection.context_resolution.work_id,
            book_version_id: inspection.context_resolution.book_version_id,
            chapter_max: inspection.context_resolution.chapter_max,
            released_evidence_ids: release?.released_evidence_ids ?? [],
          },
        }],
      }
    case 'serendipity':
      return {
        ...base,
        did: inspection.connection_decline
          ? 'Serendipity declined to surface a connection.'
          : agentTrace(turn, 'Serendipity')?.detail ?? 'Serendipity searched the permitted sources.',
        records: inspection.connection_decline
          ? [{ label: 'Connection decline', value: inspection.connection_decline }]
          : [{ label: 'Connection grants', value: { allow_connection: inspection.muse_turn.policy.allow_connection } }],
      }
    case 'provenance':
      return {
        ...base,
        did: release
          ? `Review path ${release.provenance_verdicts.join(' → ') || 'unavailable'}${release.revision_count ? `, after ${release.revision_count} revision${release.revision_count === 1 ? '' : 's'}` : ''}.`
          : 'Provenance did not complete a review for this turn.',
        records: release
          ? [{ label: 'Review outcome', value: { provenance_verdicts: release.provenance_verdicts, finding_codes: release.finding_codes, revision_count: release.revision_count } }]
          : [],
      }
    case 'release':
      return {
        ...base,
        did: release
          ? `Released as ${release.release_source.replaceAll('_', ' ')}.`
          : 'No release decision was recorded.',
        records: release ? [{ label: 'Release decision', value: release }] : [],
      }
    case 'response':
      return {
        ...base,
        did: 'The checked wording that reached the reader.',
        records: [{ label: 'Released reply', value: turn.reply }],
      }
    case 'memory':
    case 'memory_policy':
    case 'capture_review':
      return {
        ...base,
        did: release?.capture.storage === 'committed'
          ? 'One exact span was bound and committed to durable memory.'
          : `Capture did not commit (${release?.capture.storage ?? 'not applicable'}).`,
        records: [
          { label: 'Capture decision', value: release?.capture ?? null },
          { label: 'Save notice', value: turn.memory_capture },
        ],
      }
    default:
      return {
        ...base,
        did: agentTrace(turn, definition.label)?.detail ?? 'This component was not exercised on this turn.',
        records: [],
      }
  }
}

/** What actually crossed one connector on this turn. */
export function edgeDetail(edge: GraphEdge, turn: TurnRecord): ComponentDetail {
  const inspection = turn.inspection
  const release = inspection.release
  const base = {
    title: `${components[edge.source].label} → ${components[edge.target].label}`,
    role: edge.label || 'Application-owned handoff',
    receives: edge.payload,
    returns: [],
    authority: 'The application owns transport, scope and orchestration. Receiving a proposal does not grant permission to release a response or write a memory.',
  }

  if (edge.source === 'muse' && edge.target === 'librarian') {
    return { ...base, did: edge.summary, records: [{ label: 'Grounding calls', value: inspection.librarian_grounding }] }
  }
  if (edge.source === 'muse' && edge.target === 'provenance') {
    return { ...base, did: edge.summary, records: [{ label: 'Declared evidence and nomination', value: { released_evidence_ids: release?.released_evidence_ids ?? [], capture: release?.capture ?? null } }] }
  }
  if (edge.source === 'provenance' && edge.target === 'release') {
    return { ...base, did: edge.summary, records: [{ label: 'Verdicts and findings', value: { provenance_verdicts: release?.provenance_verdicts ?? [], finding_codes: release?.finding_codes ?? [] } }] }
  }
  if (edge.source === 'input' && edge.target === 'preflight') {
    return { ...base, did: edge.summary, records: [{ label: 'The message', value: inspection.muse_turn.user_message }] }
  }
  if (edge.target === 'response') {
    return { ...base, did: edge.summary, records: [{ label: 'Released reply', value: turn.reply }] }
  }
  return { ...base, did: edge.summary, records: [] }
}

export function detailFor(
  selection: { kind: 'node'; id: ComponentId } | { kind: 'edge'; id: string },
  scene: Scene,
  turn: TurnRecord,
): ComponentDetail | null {
  if (selection.kind === 'node') return componentDetail(selection.id, turn)
  const edge = scene.edges.find((item) => item.id === selection.id)
  return edge ? edgeDetail(edge, turn) : null
}
