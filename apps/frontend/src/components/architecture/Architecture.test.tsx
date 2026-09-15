import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { ProgressEvent, TurnRecord } from '../../types'
import { Architecture } from './Architecture'

/**
 * Rendering guards the seam between this application and the shared map: a
 * component id the registry does not know, or a node shape the shared layout
 * cannot place, fails here rather than in the browser.
 */

let sequence = 0

function event(
  agent: ProgressEvent['agent'],
  stage: string,
  status: ProgressEvent['status'],
): ProgressEvent {
  sequence += 1
  return {
    sequence,
    elapsed_ms: sequence * 120,
    agent,
    stage,
    status,
    detail: `${agent} ${stage} ${status}.`,
    input_origin: 'Application',
    output_receiver: 'Application',
  }
}

const progress: ProgressEvent[] = [
  event('Provenance', 'emotional_boundary_preflight', 'complete'),
  event('Librarian', 'boundary_inference', 'complete'),
  event('Muse', 'draft', 'complete'),
  event('Serendipity', 'book_corpus_search', 'complete'),
  event('Serendipity', 'web_search', 'declined'),
  event('Serendipity', 'memory_search', 'complete'),
  event('Sculptor', 'surfacing', 'complete'),
  event('Provenance', 'curation_review', 'complete'),
  event('Provenance', 'review', 'complete'),
]

function turn(): TurnRecord {
  return {
    reply: 'That pull between wanting company and wanting quiet is worth sitting with.',
    progress,
    memory_capture: null,
    trace: { trace_id: 'a'.repeat(32) },
    inspection: {
      muse_turn: {
        turn_id: 'turn-1',
        user_message: 'I finished chapter four last night.',
        reading_context: null,
        policy: {
          spoiler_ceiling: 4,
          allow_retrieval: true,
          allow_connection: true,
          allow_memory_capture: true,
          emotional_content: {
            version: '2',
            boundary_response_id: 'distressing_disclosure_v1',
            prohibit_diagnosis: true,
            stop_probing_after_distress: true,
            suppress_tools_after_distress: true,
            suppress_capture_after_distress: true,
          },
        },
      },
      context_resolution: {
        status: 'confirmed',
        work_id: 'work-1',
        work_title: 'A Book',
        book_version_id: 'rev-1',
        chapter_max: 4,
        part_id: 'main',
        unit_ids: [],
        boundary_source: 'reader_confirmed',
        boundary_authorization_basis: 'explicit_progress',
        boundary_confidence: null,
        boundary_supporting_memory_ids: [],
        boundary_supporting_locations: [],
        clarification_question: null,
        explanation: 'The reader confirmed finishing chapter four.',
      },
      traces: [],
      connection_decline: null,
      librarian_grounding: [],
      prompt: '{}',
      release: {
        release_source: 'muse_candidate',
        boundary_origin: null,
        provenance_verdicts: ['pass'],
        finding_codes: [],
        released_evidence_ids: [],
        revision_count: 0,
        failure_stage: null,
        failure_type: null,
        failure_retryable: null,
        capture: {
          nomination: 'no_candidate',
          provenance_decision: 'no_candidate',
          binding: 'not_applicable',
          storage: 'not_applicable',
          reason_code: null,
        },
      },
    },
  }
}

describe('Architecture panel', () => {
  it('invites a first message when no turn has run', () => {
    const html = renderToStaticMarkup(
      <Architecture timeline={[]} progress={[]} pendingMessage={null} />,
    )

    expect(html).toContain('No turn to map yet')
    // The page owns the surface switching now; the panel shows the live turn only.
    expect(html).toContain('saved evaluation')
    expect(html).not.toContain('role="tab"')
  })

  it('renders every component a completed turn reached', () => {
    const html = renderToStaticMarkup(
      <Architecture timeline={[turn()]} progress={[]} pendingMessage={null} />,
    )

    for (const id of ['muse', 'librarian', 'corpus', 'serendipity', 'web', 'memory', 'sculptor']) {
      expect(html).toContain(`data-node="${id}"`)
    }
    expect(html).toContain('Observed run')
    expect(html).toContain('I finished chapter four last night.')
  })

  it('marks the running component while a turn is still in flight', () => {
    const html = renderToStaticMarkup(
      <Architecture
        timeline={[]}
        progress={[event('Provenance', 'emotional_boundary_preflight', 'complete'), event('Muse', 'draft', 'running')]}
        pendingMessage="Still thinking about that ending."
      />,
    )

    expect(html).toContain('Turn in progress')
    expect(html).toContain('Still thinking about that ending.')
    expect(html).toMatch(/data-node="muse"[^>]*class="graph-node is-active"/)
    // The map must not describe an observed run as expected architecture.
    expect(html).toContain('this turn as it runs')
    expect(html).not.toContain('expected architecture')
  })
})
