import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { formatMachineLabel } from './formatMachineLabel'
import { Inspector, MemoryTableView, ReadingStateTable, TurnSummary, curationBadges } from './Inspector'
import type { StoredMemory, TurnRecord } from '../types'

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
            version: '3', boundary_response_id: 'distressing_disclosure_v1',
            self_harm_response_id: 'self_harm_disclosure_v1', prohibit_diagnosis: true,
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

  expect(html).toContain('How the turn ran')
  // Muse's 6.0s draft spent 3.0s waiting on the Serendipity search it called.
  expect(html).toContain('Time per agent: Muse 3.0s (+3.0s waiting) · Serendipity 3.0s.')
  expect(html).toContain('search rank select')
  expect(html).toContain('called by Muse')
  // Serendipity's bar starts a quarter of the way along the 6.0s turn and spans half of it.
  expect(html).toContain('left:25%;width:50%')
})

it('reads one turn as facts, then each agent once, with idle agents on one line', () => {
  const turn = exampleTurn()
  turn.inspection.context_resolution = {
    ...turn.inspection.context_resolution, status: 'confirmed', work_id: 'pg2397',
    work_title: 'The Story of My Life', chapter_max: 4, boundary_source: 'reader_confirmed',
    boundary_authorization_basis: 'explicit_progress',
    explanation: 'The reader explicitly confirmed this completed chapter in the current message.',
  }
  turn.inspection.release = { ...turn.inspection.release!, release_source: 'muse_candidate', provenance_verdicts: ['pass'] }
  turn.inspection.tool_exposure = {
    triage: { book_content: 'no', memory: 'none', override_attempt: 'no_attempt' },
    triage_failed: false, tools: ['librarian_route', 'librarian_search'], pinned_intent: null,
    book_override: true, carried_tools: [],
  }
  turn.inspection.traces = [
    { agent: 'Router', status: 'complete', detail: turn.inspection.context_resolution.explanation },
    { agent: 'Router', status: 'complete', detail: 'Turn triage: book_content=no, memory=none, override_attempt=no_attempt.' },
    { agent: 'Librarian', status: 'complete', detail: 'Muse called Librarian directly 1 time(s) for book grounding.' },
    { agent: 'Serendipity', status: 'skipped', detail: 'Muse did not call serendipity_explore for this turn.' },
    { agent: 'Provenance', status: 'complete', detail: 'Recorded review path: pass.' },
    { agent: 'Memory & Policy', status: 'not_run', detail: 'No write occurred: not_applicable.' },
  ]

  const html = renderToStaticMarkup(createElement(TurnSummary, { turn, position: 11 }))

  expect(html).toContain('Reader message 12')
  expect(html).toContain('The Story of My Life, through completed chapter 4.')
  expect(html.split('The reader explicitly confirmed').length - 1).toBe(1)
  expect(html).toContain('Needs book content: no · Needs memory: none · Override attempt: no.')
  expect(html).toContain('Book tools were offered anyway: this turn has a reading boundary')
  expect(html).not.toContain('book_content=no')
  expect(html).toContain('Provenance approved the Muse candidate (pass).')
  expect(html).not.toContain('Recorded review path')
  expect(html).not.toContain('Release decision')
  expect(html).toContain('Not used: <span><b>Serendipity</b>: Muse did not call serendipity_explore for this turn.</span>')
  expect(html).not.toContain('not_applicable')
})

it('surfaces provenance finding codes on a candidate that was corrected and released', () => {
  const turn = exampleTurn()
  turn.inspection.release = {
    ...turn.inspection.release!,
    release_source: 'muse_candidate',
    provenance_verdicts: ['revise', 'pass'],
    finding_codes: ['unresolved_evidence'],
    revision_count: 1,
  }

  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))

  expect(html).toContain('unresolved evidence')
  expect(html).toContain('cited evidence the turn never actually retrieved')
  expect(html).toContain('revise → pass')
  expect(html).toContain('1 revision')
  expect(html).toContain('corrected and released')
})

it('marks findings as blocking when the candidate was withheld', () => {
  const turn = exampleTurn()
  turn.inspection.release = {
    ...turn.inspection.release!,
    release_source: 'application_safe_decline',
    provenance_verdicts: ['reject'],
    finding_codes: ['unsupported_claim', 'spoiler'],
    revision_count: 1,
  }

  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))

  expect(html).toContain('unsupported claim')
  expect(html).toContain('spoiler')
  expect(html).toContain('withheld')
  expect(html).toContain('finding blocking')
})

it('says plainly when a clean release raised no findings', () => {
  const turn = exampleTurn()
  turn.inspection.release = {
    ...turn.inspection.release!,
    release_source: 'muse_candidate', provenance_verdicts: ['pass'],
    finding_codes: [], revision_count: 0,
  }

  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))

  expect(html).toContain('No findings were raised')
})

it('names the saved memory by ID on a turn recorded before the memory table existed', () => {
  const turn = exampleTurn()
  turn.inspection.release!.capture = {
    nomination: 'candidate', provenance_decision: 'allow_capture', binding: 'exact',
    storage: 'committed', reason_code: null,
  }
  turn.inspection.memory = { active_count: 2, captured_memory_id: 'mem_abc123', cited_memory_ids: [] }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('Muse proposed a memory, Provenance allowed it, and policy saved it.')
  expect(html).toMatch(/<dt>Saved this turn<\/dt><dd><code>mem_abc123<\/code>/)
  expect(html).toContain('2 saved memories were available to this turn.')
})

it('tables both reading-progress stores as the latest turn recorded them', () => {
  const older = exampleTurn()
  older.inspection.reading_state = { session: null, saved: [] }
  const latest = exampleTurn()
  latest.inspection.reading_state = {
    session: { work_id: 'pg2397', title: 'The Story of My Life', part_id: 'main', chapter_max: 4 },
    saved: [
      { work_id: 'pg23', title: 'Narrative of the Life of Frederick Douglass', part_id: 'main', chapter_max: 7 },
      { work_id: 'pg2397', title: 'The Story of My Life', part_id: 'main', chapter_max: 4 },
    ],
  }
  const html = renderToStaticMarkup(createElement(ReadingStateTable, { timeline: [older, latest, exampleTurn()] }))
  expect(html).toContain('As recorded after reader message 02')
  const rows = [...html.matchAll(/<tr><td>([^<]+)<\/td><td>([^<]+)<\/td><td>([^<]+)<\/td><\/tr>/g)].map((row) => row.slice(1))
  expect(rows).toEqual([
    ['This conversation', 'The Story of My Life', 'Chapter 4'],
    ['Saved to account', 'Narrative of the Life of Frederick Douglass', 'Chapter 7'],
    ['Saved to account', 'The Story of My Life', 'Chapter 4'],
  ])
  expect(renderToStaticMarkup(createElement(ReadingStateTable, { timeline: [exampleTurn()] }))).toContain('No turn here recorded reading progress')
})

it('shortens long memory IDs and keeps the full ID on hover', () => {
  const turn = exampleTurn()
  const id = 'mem_99ced7b9e29592548b4c7dd5f4d9efd7cc25ac9406006fb0ae351f1d304e9a81'
  turn.inspection.memory = { active_count: 1, captured_memory_id: id, cited_memory_ids: [] }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain(`<code title="${id}">mem_99ced7b9e295…</code>`)
})

function turnWithMemoryStore(): TurnRecord {
  const turn = exampleTurn()
  turn.inspection.muse_turn.turn_id = 'turn-new'
  turn.inspection.memory = {
    active_count: 2,
    captured_memory_id: 'mem_new',
    cited_memory_ids: ['summary_abc'],
    available_memories: [
      { memory_id: 'mem_old', kind: 'original', source_memory_ids: ['mem_old'] },
      { memory_id: 'summary_abc', kind: 'derived_summary', source_memory_ids: ['mem_old', 'mem_retired'] },
    ],
    texts: { mem_old: 'I reread letters when homesick.', summary_abc: 'Rereads letters to feel close.' },
  }
  return turn
}

it('says what Sculptor did after the save', () => {
  const turn = turnWithMemoryStore()
  turn.inspection.release!.capture = {
    nomination: 'candidate', provenance_decision: 'allow_capture', binding: 'exact',
    storage: 'committed', reason_code: null, curation_status: 'applied',
  }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('Sculptor proposed a change, Provenance allowed it, and it was applied.')
})

it('shows the curation Sculptor proposed and why Provenance did not apply it', () => {
  const turn = turnWithMemoryStore()
  turn.inspection.dev_trace = {
    connection_events: [],
    agent_exchanges: [
      {
        role: 'Sculptor', stage: 'curation', skill: 'sculptor.memory-curation', input_prompt: '{}', status: 'success',
        output: { kind: 'curation_proposal', action: { action: 'assign_topic_group', topic_label: 'Library habits', source_memory_ids: ['mem_old', 'mem_new'] } },
      },
      {
        role: 'Provenance', stage: 'curation_review', skill: 'provenance.curation-review', input_prompt: '{}', status: 'success',
        output: { decision: 'revise', findings: [{ code: 'incoherent_topic', explanation: 'The guitar memory does not share the theme.' }] },
      },
    ],
  }
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turn] }))
  expect(html).toContain('Sculptor proposed: Topic group “Library habits”')
  expect(html).toMatch(/Over <code>mem_old<\/code><code>mem_new<\/code>/)
  expect(html).toContain('Provenance: revise')
  expect(html).toContain('The guitar memory does not share the theme.')
})

it('lists only the memory IDs a turn saved, used, and could search', () => {
  const html = renderToStaticMarkup(createElement(Inspector, { timeline: [turnWithMemoryStore()] }))
  expect(html).toMatch(/<dt>Saved this turn<\/dt><dd><code>mem_new<\/code><\/dd>/)
  expect(html).toMatch(/<dt>Used in the reply<\/dt><dd><code>summary_abc<\/code><\/dd>/)
  expect(html).toMatch(/<dt>Searchable this turn \(2\)<\/dt><dd><code>mem_old<\/code><code>summary_abc<\/code><\/dd>/)
  expect(html).not.toContain('mem_retired')
  expect(html).not.toContain('I reread letters')
})

const STORED: StoredMemory[] = [
  { memory_id: 'mem_new', kind: 'original', created_at: '2026-10-04T09:00:00+00:00', source_turn_id: 'turn-new', source_prop_id: null, source_memory_ids: ['mem_new'], searchable: true, text: null, topic_labels: [] },
  { memory_id: 'summary_abc', kind: 'derived_summary', created_at: '2026-10-03T09:00:00+00:00', source_turn_id: null, source_prop_id: null, source_memory_ids: ['mem_old', 'mem_retired'], searchable: true, text: 'Rereads letters to feel close.', topic_labels: [] },
  { memory_id: 'mem_retired', kind: 'original', created_at: '2026-10-02T09:00:00+00:00', source_turn_id: 'turn-elsewhere', source_prop_id: null, source_memory_ids: ['mem_retired'], searchable: false, text: null, topic_labels: [] },
  { memory_id: 'mem_prop', kind: 'original', created_at: '2026-10-01T09:00:00+00:00', source_turn_id: null, source_prop_id: 'prop-05', source_memory_ids: ['mem_prop'], searchable: true, text: null, topic_labels: [] },
]

it('tables every memory with when it was stored and its source, and offers Forget only on originals', () => {
  const html = renderToStaticMarkup(createElement(MemoryTableView, {
    rows: STORED, timeline: [turnWithMemoryStore()], forgetting: null, onForget: () => {},
  }))
  expect(html).toContain('4 memories, 1 retired')
  const rows = [...html.matchAll(/<tr( class="is-retired")?><td><time dateTime="([^"]+)">.*?<td class="memory-id"><code[^>]*>([^<]+)<\/code><\/td><td class="memory-text">([^<]+)<\/td><td>([^<]+)<\/td><td>([^<]+)<\/td><td><span[^>]*>([^<]+)<\/span><\/td><td class="memory-curation">(.*?)<\/td><td>(.*?)<\/td><\/tr>/g)]
    .map((row) => [row[3], row[2], row[5], row[6], row[7], row[8].split(/<[^>]*>/).join(''), row[4], row[9].includes('Forget')])
  expect(rows).toEqual([
    ['mem_new', '2026-10-04T09:00:00+00:00', 'Original', 'Reader message 01', 'Searchable', '—', '—', true],
    ['summary_abc', '2026-10-03T09:00:00+00:00', 'Summary', 'Curated from mem_old, mem_retired', 'Searchable', 'Covers 2 memories', 'Rereads letters to feel close.', false],
    ['mem_retired', '2026-10-02T09:00:00+00:00', 'Original', 'Another conversation', 'Retired', 'In summary', '—', true],
    ['mem_prop', '2026-10-01T09:00:00+00:00', 'Original', 'Scenario Prop prop-05', 'Searchable', '—', '—', true],
  ])
  expect(html).not.toContain('apps.backend.show_memories')
})

const LINKED: StoredMemory[] = [
  { ...STORED[3], memory_id: 'mem_kept', duplicate_memory_ids: ['mem_copy'] },
  { ...STORED[2], memory_id: 'mem_copy', duplicate_memory_ids: ['mem_kept'], retired_for: 'mem_kept' },
  { ...STORED[3], memory_id: 'mem_open', source_prop_id: 'prop-06' },
  { ...STORED[1], memory_id: 'topic_x', kind: 'topic_group', text: null, topic_labels: ['Open house'], source_memory_ids: ['mem_open', 'mem_kept'] },
]

it('tags every curation link a row takes part in, each highlighting its own group', () => {
  const byId = Object.fromEntries(LINKED.map((row) => [row.memory_id, curationBadges(row, LINKED)]))
  const view = (id: string) => byId[id].map((badge) => [badge.label, [...badge.highlight.ids].sort()])
  expect(view('mem_kept')).toEqual([
    ['Topic · Open house', ['mem_kept', 'mem_open', 'topic_x']],
    ['Duplicate of mem_copy', ['mem_copy', 'mem_kept']],
  ])
  expect(view('mem_copy')).toEqual([['Retired · duplicate of mem_kept', ['mem_copy', 'mem_kept']]])
  expect(view('topic_x')).toEqual([['Covers 2 memories', ['mem_kept', 'mem_open', 'topic_x']]])
  // Both ends of one duplicate link highlight the same group.
  expect(byId.mem_kept[1].highlight.key).toBe(byId.mem_copy[0].highlight.key)
})

it('keeps rows in stored order and lists applied curation as a history', () => {
  const html = renderToStaticMarkup(createElement(MemoryTableView, {
    rows: LINKED,
    timeline: [],
    history: [
      { event_id: 'cur_1', applied_at: '2026-10-05T09:00:00+00:00', action: 'link_duplicates', source_memory_ids: ['mem_kept', 'mem_copy'], result_memory_id: null, memory_id: null, canonical_memory_id: null, text: null },
      { event_id: 'cur_2', applied_at: '2026-10-05T09:01:00+00:00', action: 'tombstone_for_retrieval', source_memory_ids: ['mem_copy', 'mem_kept'], result_memory_id: null, memory_id: 'mem_copy', canonical_memory_id: 'mem_kept', text: null },
      { event_id: 'cur_3', applied_at: '2026-10-05T09:02:00+00:00', action: 'restore_to_retrieval', source_memory_ids: ['mem_copy'], result_memory_id: null, memory_id: 'mem_copy', canonical_memory_id: null, text: null },
    ],
  }))
  expect([...html.matchAll(/<tr[^>]*><td><time[^>]*>.*?<code>([^<]+)<\/code>/g)].map((row) => row[1]))
    .toEqual(['mem_kept', 'mem_copy', 'mem_open', 'topic_x'])
  expect(html).toContain('Linked mem_kept and mem_copy as duplicates')
  expect(html).toContain('Retired mem_copy from search; mem_kept stays searchable')
  expect(html).toContain('Restored mem_copy to search')
  expect(html).not.toContain('Last curation')
})

it('disables every Forget button while one memory is being forgotten', () => {
  const html = renderToStaticMarkup(createElement(MemoryTableView, {
    rows: STORED, timeline: [], forgetting: 'mem_new', onForget: () => {},
  }))
  expect(html).toContain('Forgetting…')
  expect(html.match(/<button[^>]*disabled=""[^>]*>/g)).toHaveLength(3)
})

it('shows a recorded run read-only: no Forget, its own note, and undated Props', () => {
  const html = renderToStaticMarkup(createElement(MemoryTableView, {
    rows: [{ ...STORED[3], created_at: '', text: 'My kiln notebook is in the second drawer.' }],
    timeline: [],
    note: 'Recorded run note.',
  }))
  expect(html).toContain('Recorded run note.')
  expect(html).toContain('Undated')
  expect(html).toContain('Scenario Prop prop-05')
  expect(html).not.toContain('Forget')
  expect(html).not.toContain('LINGER_DEV_INSPECT')
})

it('reads a no-book turn without restating the boundary, release, or decline', () => {
  const turn = exampleTurn()
  turn.inspection.release = { ...turn.inspection.release!, release_source: 'muse_candidate', provenance_verdicts: ['pass'] }
  turn.inspection.connection_decline = { reason: 'no_matching_memory', failure_code: null }
  turn.inspection.traces = [
    { agent: 'Serendipity', status: 'declined', detail: 'Serendipity returned a typed decline; no diagnostic content was exposed.' },
    { agent: 'Muse', status: 'complete', detail: 'Provenance and deterministic release validation approved the candidate that was released.' },
    { agent: 'Provenance', status: 'complete', detail: 'Recorded review path: pass.' },
  ]
  const at = (sequence: number, elapsed_ms: number, agent: 'Muse' | 'Provenance' | 'Serendipity', stage: string, status: 'running' | 'complete', input_origin: 'Application' | 'Muse' = 'Application') => (
    { sequence, elapsed_ms, agent, stage, status, detail: '', input_origin, output_receiver: input_origin }
  )
  turn.progress = [
    at(1, 0, 'Provenance', 'emotional_boundary_preflight', 'running'),
    at(2, 3000, 'Provenance', 'emotional_boundary_preflight', 'complete'),
    at(3, 3000, 'Muse', 'draft', 'running'),
    at(4, 5000, 'Serendipity', 'memory_recall', 'running', 'Muse'),
    at(5, 9000, 'Serendipity', 'memory_recall', 'complete', 'Muse'),
    at(6, 12000, 'Muse', 'draft', 'complete'),
  ]

  const html = renderToStaticMarkup(createElement(TurnSummary, { turn, position: 6 }))

  expect(html).toContain('No book in play')
  expect(html).not.toContain('No confirmed book')
  expect(html).toContain('Drafted the reply that was released, calling Serendipity.')
  expect(html).not.toContain('deterministic release validation')
  expect(html).toContain('The emotional-boundary preflight let reflection continue.')
  expect(html).toContain('Declined to surface a connection: no matching memory.')
  expect(html).not.toContain('typed decline')
  expect(html).not.toContain('Connection contract')
  expect(html).toContain('Time per agent: Provenance 3.0s · Muse 5.0s (+4.0s waiting) · Serendipity 4.0s.')
})
