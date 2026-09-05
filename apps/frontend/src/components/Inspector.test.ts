import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { formatMachineLabel } from './formatMachineLabel'
import { Inspector } from './Inspector'
import type { ChatResult } from '../types'

describe('formatMachineLabel', () => {
  it('formats every segment of a multiword failure stage', () => {
    expect(formatMachineLabel('emotional_boundary_preflight')).toBe('emotional boundary preflight')
  })
})

it('renders an application clarification as a successful question, not a decline', () => {
  const turn: ChatResult = {
    reply: 'How far have you read?',
    trace: { trace_id: '0123456789abcdef0123456789abcdef' },
    memory_capture: null,
    inspection: {
      muse_turn: {
        turn_id: 'clarification-test', user_message: 'Why does Alice change?', reading_context: null,
        policy: {
          spoiler_ceiling: null, allow_retrieval: false, allow_connection: false, allow_memory_capture: false,
          emotional_content: {
            version: '1', boundary_response_id: 'distressing_disclosure_v1', prohibit_diagnosis: true,
            stop_probing_after_distress: true, suppress_tools: true, suppress_capture: true,
          },
        },
      },
      context_resolution: {
        status: 'unknown', work_id: null, work_title: null, book_version_id: null, chapter_max: null,
        boundary_source: null, boundary_authorization_basis: null, boundary_confidence: null,
        boundary_supporting_memory_ids: [], boundary_supporting_locations: [],
        clarification_question: null, explanation: 'No confirmed reading boundary.',
      },
      traces: [], connection_decline: null, librarian_grounding: [], prompt: '{}',
      release: {
        release_source: 'application_clarification', boundary_origin: null, provenance_verdicts: ['pass'],
        finding_codes: [], released_evidence_ids: [], revision_count: 0,
        failure_stage: null, failure_type: null, failure_retryable: null,
        capture: {
          nomination: 'no_candidate', provenance_decision: 'no_candidate', binding: 'not_applicable',
          storage: 'not_applicable', reason_code: 'not_applicable',
        },
      },
    },
  }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('Clarification requested')
  expect(html).toContain('validated question after safety review')
  expect(html).toContain('How far have you read?')
  expect(html).not.toContain('Safe decline released')
})
