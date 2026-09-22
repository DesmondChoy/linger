import { describe, expect, it } from 'vitest'
import type { TurnRecord } from '../../types'
import { componentDetail, edgeDetail } from './turnDetail'

/**
 * Opening a component must show what it carried on THIS turn. A description of
 * the role is the fallback under the data, never the answer.
 */
function turn(): TurnRecord {
  return {
    reply: 'That pull between meaning to change and not changing is worth sitting with.',
    progress: [],
    memory_capture: { notice: 'Saved to your memories.' },
    trace: { trace_id: 'c'.repeat(32) },
    inspection: {
      muse_turn: {
        turn_id: '1612bb0e-2829-4f00-8db2-b567b9d4e53c',
        user_message: "Pinocchio keeps meaning to do better and then not doing it. Does that link to anything I've said before?",
        reading_context: null,
        policy: {
          spoiler_ceiling: null,
          allow_retrieval: false,
          allow_connection: true,
          allow_memory_capture: true,
          emotional_content: {
            version: '3',
            boundary_response_id: 'distressing_disclosure_v1',
            self_harm_response_id: 'self_harm_disclosure_v1',
            prohibit_diagnosis: true,
            stop_probing_after_distress: true,
            suppress_tools_after_distress: true,
            suppress_capture_after_distress: true,
          },
        },
      },
      context_resolution: {
        status: 'unknown', work_id: null, work_title: null, book_version_id: null,
        chapter_max: null, part_id: 'main', unit_ids: [], boundary_source: null,
        boundary_authorization_basis: null, boundary_confidence: null,
        boundary_supporting_memory_ids: [], boundary_supporting_locations: [],
        clarification_question: null, explanation: 'No book context was established.',
      },
      traces: [{ agent: 'Muse', status: 'complete', detail: 'Muse drafted a reflection.' }],
      connection_decline: null,
      librarian_grounding: [],
      prompt: '{"cue":"..."}',
      release: {
        release_source: 'muse_candidate', boundary_origin: null,
        provenance_verdicts: ['revise', 'pass'], finding_codes: ['unsupported_claim'],
        released_evidence_ids: [], revision_count: 1,
        failure_stage: null, failure_type: null, failure_retryable: null,
        capture: {
          nomination: 'candidate', provenance_decision: 'allow_capture',
          binding: 'exact', storage: 'committed', reason_code: null,
        },
      },
    },
  }
}

describe('componentDetail', () => {
  it('opens Muse on the turn contract itself, not a description of Muse', () => {
    const detail = componentDetail('muse', turn())
    const contract = detail.records.find((record) => record.label === 'MuseTurn contract')

    expect(contract).toBeDefined()
    const json = JSON.stringify(contract?.value)
    expect(json).toContain('1612bb0e-2829-4f00-8db2-b567b9d4e53c')
    expect(json).toContain('"allow_connection":true')
    expect(json).toContain('distressing_disclosure_v1')
    // The standing contract is still available, but underneath the run data.
    expect(detail.authority).toContain('Cannot release its own response')
  })

  it('carries the assembled input alongside the contract', () => {
    expect(componentDetail('muse', turn()).records.map((record) => record.label))
      .toEqual(['MuseTurn contract', 'Assembled dynamic input'])
  })

  it('reports the review path and findings on Provenance', () => {
    const detail = componentDetail('provenance', turn())
    expect(detail.did).toContain('revise → pass')
    expect(detail.did).toContain('1 revision')
    expect(JSON.stringify(detail.records[0].value)).toContain('unsupported_claim')
  })

  it('reports a committed capture on the memory components', () => {
    const detail = componentDetail('memory_policy', turn())
    expect(detail.did).toContain('committed to durable memory')
    expect(JSON.stringify(detail.records[0].value)).toContain('"storage":"committed"')
  })

  it('says plainly when a component had nothing to do this turn', () => {
    expect(componentDetail('corpus', turn()).did).toContain('No corpus passage')
  })

  it('shows the emotional policy in force on the preflight', () => {
    const detail = componentDetail('preflight', turn())
    expect(detail.did).toContain('allowed ordinary reflection')
    expect(JSON.stringify(detail.records[0].value)).toContain('prohibit_diagnosis')
  })
})

describe('edgeDetail', () => {
  const edge = {
    id: 'provenance-release', source: 'provenance' as const, target: 'release' as const,
    label: 'Review', summary: 'Review does not release its own candidate.', payload: ['Response verdict'],
  }

  it('shows what crossed the connector on this turn', () => {
    const detail = edgeDetail(edge, turn())
    expect(detail.title).toBe('Provenance → Release checks')
    expect(JSON.stringify(detail.records[0].value)).toContain('unsupported_claim')
  })
})
