import { describe, expect, it } from 'vitest'
import type { CaptureInspection, ProgressEvent, TurnRecord } from '../../types'
import { buildLiveTurn } from './liveScene'

let sequence = 0

function event(
  agent: ProgressEvent['agent'],
  stage: string,
  status: ProgressEvent['status'],
  elapsed_ms = ++sequence * 100,
): ProgressEvent {
  return {
    sequence: sequence,
    elapsed_ms,
    agent,
    stage,
    status,
    detail: `${agent} ${stage} ${status}.`,
    input_origin: 'Application',
    output_receiver: 'Application',
  }
}

function build(events: ProgressEvent[]) {
  return buildLiveTurn({ events, userMessage: 'I finished chapter four last night.' })
}

const reflection = [
  event('Provenance', 'emotional_boundary_preflight', 'running'),
  event('Provenance', 'emotional_boundary_preflight', 'complete'),
  event('Muse', 'draft', 'running'),
  event('Muse', 'draft', 'complete'),
  event('Provenance', 'review', 'running'),
  event('Provenance', 'review', 'complete'),
]

describe('buildLiveTurn', () => {
  it('shows only the always-run spine when the turn reached no source', () => {
    const { scene } = build(reflection)

    expect(scene.nodes.map((node) => node.id)).toEqual([
      'input', 'preflight', 'muse', 'provenance', 'release', 'response',
    ])
    expect(scene.edges.map((edge) => edge.id)).toEqual([
      'input-preflight', 'preflight-muse', 'muse-provenance', 'provenance-release', 'release-response',
    ])
  })

  it('adds the connection sources a Serendipity turn actually reached', () => {
    const { scene } = build([
      ...reflection,
      event('Serendipity', 'search_rank_select', 'running'),
      event('Serendipity', 'book_corpus_search', 'complete'),
      event('Serendipity', 'web_search', 'complete'),
      event('Serendipity', 'search_rank_select', 'complete'),
    ])
    const ids = scene.nodes.map((node) => node.id)

    expect(ids).toContain('serendipity')
    expect(ids).toContain('librarian')
    expect(ids).toContain('corpus')
    expect(ids).toContain('web')
    // A memory search never ran, so that source stays off the map.
    expect(ids).not.toContain('memory')
    expect(scene.edges.map((edge) => edge.id)).toEqual(expect.arrayContaining([
      'muse-serendipity', 'serendipity-librarian', 'librarian-corpus', 'serendipity-web',
    ]))
    expect(scene.edges.map((edge) => edge.id)).not.toContain('serendipity-memory')
  })

  it('never draws an edge to a component the turn did not use', () => {
    const { scene } = build([
      ...reflection,
      event('Serendipity', 'memory_search', 'declined'),
    ])
    const ids = new Set(scene.nodes.map((node) => node.id))

    for (const edge of scene.edges) {
      expect(ids.has(edge.source)).toBe(true)
      expect(ids.has(edge.target)).toBe(true)
    }
  })

  it('reports a component as running until its last stage settles', () => {
    const midTurn = build([
      event('Provenance', 'emotional_boundary_preflight', 'complete'),
      event('Muse', 'draft', 'running'),
    ])

    expect(midTurn.running).toBe(true)
    expect(midTurn.active?.nodes).toEqual(['muse'])
    expect(midTurn.activity.find((item) => item.id === 'muse')?.status).toBe('running')
    expect(midTurn.activity.find((item) => item.id === 'preflight')?.status).toBe('complete')

    const settled = build(reflection)
    expect(settled.running).toBe(false)
    expect(settled.active).toBeNull()
  })

  it('lets a failed stage outrank a completed sibling on the same component', () => {
    const { activity } = build([
      event('Muse', 'draft', 'complete'),
      event('Muse', 'revision', 'failed'),
    ])

    expect(activity.find((item) => item.id === 'muse')?.status).toBe('failed')
  })

  it('collapses repeated reports of one stage into a single entry', () => {
    const { activity } = build([
      event('Muse', 'draft', 'running'),
      event('Muse', 'draft', 'complete'),
    ])
    const muse = activity.find((item) => item.id === 'muse')

    expect(muse?.stages).toHaveLength(1)
    expect(muse?.stages[0]).toMatchObject({ stage: 'draft', status: 'complete' })
  })

  it('replays the settled stages as an ordered walkthrough between entry and release', () => {
    const { scene } = build(reflection)

    expect(scene.steps[0].nodes).toEqual(['input', 'preflight'])
    expect(scene.steps.at(-1)?.nodes).toEqual(['release', 'response'])
    // One step per settled stage; the three "running" reports add nothing.
    expect(scene.steps.map((step) => step.title)).toEqual([
      'Your message enters the turn',
      'Provenance · emotional boundary preflight',
      'Muse · draft',
      'Provenance · review',
      'The application released the reply',
    ])
  })

  it('falls back to the reporting agent when a stage name is unrecognised', () => {
    const { activity } = build([event('Sculptor', 'processing', 'complete')])

    expect(activity.map((item) => item.id)).toEqual(['sculptor'])
  })

  it('describes an empty stream without inventing activity', () => {
    const { scene, activity, running } = build([])

    expect(activity).toEqual([])
    expect(running).toBe(false)
    expect(scene.summary).toBe('Waiting for the first stage of this turn.')
    expect(scene.nodes).toHaveLength(6)
  })
})

describe('memory capture on the live map', () => {
  function turnWithCapture(capture: CaptureInspection): TurnRecord {
    return {
      reply: 'Reply.',
      progress: reflection,
      memory_capture: null,
      trace: { trace_id: 'a'.repeat(32) },
      inspection: {
        muse_turn: { turn_id: 'turn-capture', user_message: 'I fill silence.' },
        release: { release_source: 'muse_candidate', provenance_verdicts: ['pass'], finding_codes: [], capture },
      },
    } as unknown as TurnRecord
  }

  it('draws Memory & Policy after Provenance when a memory was saved', () => {
    const { scene } = buildLiveTurn({
      events: reflection,
      userMessage: 'I fill silence.',
      turn: turnWithCapture({ nomination: 'candidate', provenance_decision: 'allow_capture', binding: 'exact', storage: 'committed', reason_code: null }),
    })
    const node = scene.nodes.find((item) => item.id === 'memory_policy')
    expect(node?.footer?.right).toBe('saved')
    expect(scene.edges.map((item) => item.id)).toContain('provenance-memory_policy')
  })

  it('leaves Memory & Policy off when Muse proposed nothing', () => {
    const { scene } = buildLiveTurn({
      events: reflection,
      userMessage: 'I fill silence.',
      turn: turnWithCapture({ nomination: 'no_candidate', provenance_decision: 'no_candidate', binding: 'not_applicable', storage: 'not_applicable', reason_code: 'not_applicable' }),
    })
    expect(scene.nodes.some((item) => item.id === 'memory_policy')).toBe(false)
  })
})
