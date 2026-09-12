import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { formatMachineLabel } from './formatMachineLabel'
import { Inspector } from './Inspector'
import type { TurnRecord } from '../types'

describe('formatMachineLabel', () => {
  it('formats every segment of a multiword failure stage', () => {
    expect(formatMachineLabel('emotional_boundary_preflight')).toBe('emotional boundary preflight')
  })
})

function exampleTurn(): TurnRecord {
  return {
    reply: 'How far have you read?',
    trace: { trace_id: '0123456789abcdef0123456789abcdef' },
    memory_capture: null,
    progress: [],
    inspection: {
      muse_turn: {
        turn_id: 'clarification-test', user_message: 'Why does Alice change?', reading_context: null,
        policy: {
          spoiler_ceiling: null, allow_retrieval: false, allow_connection: false, allow_memory_capture: false,
          emotional_content: {
            version: '2', boundary_response_id: 'distressing_disclosure_v1', prohibit_diagnosis: true,
            stop_probing_after_distress: true,
            suppress_tools_after_distress: true, suppress_capture_after_distress: true,
          },
        },
      },
      context_resolution: {
        status: 'unknown', work_id: null, work_title: null, book_version_id: null, chapter_max: null, part_id: 'main', unit_ids: [],
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
}

it('renders an application clarification as a successful question, not a decline', () => {
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [exampleTurn()] }))
  expect(html).toContain('Clarification requested')
  expect(html).toContain('validated question after safety review')
  expect(html).toContain('How far have you read?')
  expect(html).not.toContain('Safe decline released')
})


it('shows an exact letter boundary without claiming retrieval is off or inventing a chapter', () => {
  const turn = exampleTurn()
  turn.inspection.context_resolution = {
    ...turn.inspection.context_resolution, status: 'confirmed', work_id: 'pg2397',
    work_title: 'The Story of My Life', chapter_max: null, part_id: 'letters',
    unit_ids: ['pg2397-vb3cc1e13-sec027'], boundary_source: 'reader_confirmed',
    boundary_authorization_basis: 'explicit_progress',
  }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('only the named reading location explicitly completed in letters')
  expect(html).not.toContain('retrieval is off')
  expect(html).not.toContain('Chapter null')
})

it('distinguishes the supplementary part in a chapter boundary', () => {
  const turn = exampleTurn()
  turn.inspection.context_resolution = {
    ...turn.inspection.context_resolution, status: 'confirmed', work_id: 'pg2397',
    work_title: 'The Story of My Life', chapter_max: 1, part_id: 'part-iii',
    boundary_source: 'reader_confirmed', boundary_authorization_basis: 'explicit_progress',
  }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('through completed chapter 1 in Part III')
})

it('renders per-agent seconds and the handoffs between agents', () => {
  const turn = exampleTurn()
  turn.progress = [
    {
      sequence: 1, elapsed_ms: 0, agent: 'Muse', stage: 'draft', status: 'running',
      detail: 'Muse candidate generation is in progress.',
      input_origin: 'Application', output_receiver: 'Application',
    },
    {
      sequence: 2, elapsed_ms: 1500, agent: 'Serendipity', stage: 'search_rank_select',
      status: 'running', detail: 'Serendipity search and comparison is in progress.',
      input_origin: 'Muse', output_receiver: 'Muse',
    },
    {
      sequence: 3, elapsed_ms: 4500, agent: 'Serendipity', stage: 'search_rank_select',
      status: 'complete', detail: 'Serendipity search and comparison completed.',
      input_origin: 'Muse', output_receiver: 'Muse',
    },
    {
      sequence: 4, elapsed_ms: 6000, agent: 'Muse', stage: 'draft', status: 'complete',
      detail: 'Muse candidate generation completed.',
      input_origin: 'Application', output_receiver: 'Application',
    },
  ]

  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))

  expect(html).toContain('Agent timing and handoffs')
  // Per-agent totals: Muse ran the whole 6.0s span, Serendipity 3.0s of it.
  expect(html).toContain('6.0s')
  expect(html).toContain('3.0s')
  expect(html).toContain('search rank select')
})
