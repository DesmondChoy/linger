import { describe, expect, it } from 'vitest'
import type { ProgressEvent } from '../types'
import { formatSeconds, toAgentSteps, toAgentTotals } from './progressSummary'

let sequence = 0

function event(overrides: Partial<ProgressEvent>): ProgressEvent {
  sequence += 1
  return {
    sequence,
    elapsed_ms: 0,
    agent: 'Muse',
    stage: 'draft',
    status: 'running',
    detail: 'detail',
    input_origin: 'Application',
    output_receiver: 'Application',
    ...overrides,
  }
}

describe('toAgentSteps', () => {
  it('measures a stage from its running event to its terminal event', () => {
    const steps = toAgentSteps([
      event({ agent: 'Muse', stage: 'draft', status: 'running', elapsed_ms: 500 }),
      event({ agent: 'Muse', stage: 'draft', status: 'complete', elapsed_ms: 3200 }),
    ])

    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({
      agent: 'Muse',
      stage: 'draft',
      status: 'complete',
      startedMs: 500,
      durationMs: 2700,
    })
  })

  it('keeps interleaved agents on their own stages', () => {
    const steps = toAgentSteps([
      event({ agent: 'Muse', stage: 'draft', status: 'running', elapsed_ms: 0 }),
      event({ agent: 'Serendipity', stage: 'search_rank_select', status: 'running', elapsed_ms: 100 }),
      event({ agent: 'Serendipity', stage: 'search_rank_select', status: 'complete', elapsed_ms: 900 }),
      event({ agent: 'Muse', stage: 'draft', status: 'complete', elapsed_ms: 1500 }),
    ])

    expect(steps.map((step) => [step.agent, step.durationMs])).toEqual([
      ['Muse', 1500],
      ['Serendipity', 800],
    ])
  })

  it('reports a stage that is still running without a duration', () => {
    const steps = toAgentSteps([
      event({ agent: 'Provenance', stage: 'review', status: 'running', elapsed_ms: 400 }),
    ])

    expect(steps[0]).toMatchObject({ status: 'running', durationMs: null })
  })

  it('never invents a duration for a stage reported only once', () => {
    // Serendipity's individual searches emit a single terminal event.
    const steps = toAgentSteps([
      event({
        agent: 'Serendipity',
        stage: 'book_corpus_search',
        status: 'complete',
        elapsed_ms: 2200,
        input_origin: 'Serendipity',
        output_receiver: 'Librarian',
      }),
    ])

    expect(steps[0]).toMatchObject({
      durationMs: null,
      startedMs: 2200,
      from: 'Serendipity',
      to: 'Librarian',
    })
  })

  it('carries the handoff direction through to the step', () => {
    const steps = toAgentSteps([
      event({
        agent: 'Serendipity',
        stage: 'search_rank_select',
        status: 'running',
        input_origin: 'Muse',
        output_receiver: 'Muse',
      }),
    ])

    expect(steps[0]).toMatchObject({ from: 'Muse', to: 'Muse' })
  })
})

describe('toAgentTotals', () => {
  it('sums measured time per agent and flags unmeasured stages', () => {
    const totals = toAgentTotals(toAgentSteps([
      event({ agent: 'Muse', stage: 'draft', status: 'running', elapsed_ms: 0 }),
      event({ agent: 'Muse', stage: 'draft', status: 'complete', elapsed_ms: 1000 }),
      event({ agent: 'Muse', stage: 'revision', status: 'running', elapsed_ms: 1000 }),
      event({ agent: 'Muse', stage: 'revision', status: 'complete', elapsed_ms: 2500 }),
      event({ agent: 'Serendipity', stage: 'web_search', status: 'complete', elapsed_ms: 3000 }),
    ]))

    expect(totals).toEqual([
      { agent: 'Muse', durationMs: 2500, steps: 2, partial: false },
      { agent: 'Serendipity', durationMs: 0, steps: 1, partial: true },
    ])
  })
})

describe('formatSeconds', () => {
  it('renders tenths of a second', () => {
    expect(formatSeconds(0)).toBe('0.0s')
    expect(formatSeconds(2750)).toBe('2.8s')
  })
})
