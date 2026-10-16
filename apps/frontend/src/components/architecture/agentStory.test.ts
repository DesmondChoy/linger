import { describe, expect, it } from 'vitest'
import type { AgentExchange, TurnRecord } from '../../types'
import { agentStory } from './agentStory'

function run(role: string, stage: string, output: unknown, steps: AgentExchange['steps'] = []): AgentExchange {
  return { role, stage, skill: null, input_prompt: '{}', status: 'success', steps, output }
}

function turn(releaseSource = 'muse_candidate', grounding = 0): TurnRecord {
  return {
    inspection: {
      release: { release_source: releaseSource },
      context_resolution: { work_id: 'pg11', work_title: "Alice's Adventures in Wonderland" },
      librarian_grounding: Array.from({ length: grounding }, () => ({})),
    },
  } as unknown as TurnRecord
}

const FINDING = {
  code: 'unsupported_claim',
  applies_to: 'response',
  explanation: 'The reader never said how many days they ride.',
}

describe('agentStory', () => {
  it('retells the emotional preflight as a decision about the turn', () => {
    const story = agentStory('preflight', [run('Provenance', 'emotional_boundary_preflight', { decision: 'apply_boundary' })], turn())

    expect(story?.summary).toBe('Signs of distress, so Linger sent a fixed boundary message.')
    expect(story?.steps).toEqual([
      'Before anything else ran, Provenance read your message for signs of distress and found signs of distress, so Linger answered with a fixed, supportive message instead of reflecting on the book.',
    ])
  })

  it('walks through Muse sorting, asking for help, drafting, nominating and revising', () => {
    const runs = [
      run('Muse', 'turn_triage', { book_content: 'no', memory: 'own_earlier_reflections', override_attempt: 'no_attempt' }),
      run('Muse', 'draft', {
        reply: 'You read about forty minutes a day.',
        evidence_uses: [{ source_kind: 'session_line' }, { source_kind: 'memory' }, { source_kind: 'memory' }],
        memory: { kind: 'memory_candidate', text: 'I read on the train.', reason_code: 'stable_preference_or_intention' },
      }, [
        { kind: 'tool-call', tool: 'serendipity_explore', args: '{"intent":"recall_memory"}' },
        { kind: 'tool-return', tool: 'serendipity_explore', content: {} },
        { kind: 'tool-call', tool: 'final_result', args: '{}' },
      ]),
      run('Muse', 'revision', { reply: 'You read about forty minutes per round trip.', evidence_uses: [] }),
    ]

    const story = agentStory('muse', runs, turn())

    expect(story?.summary).toBe('Muse drafted the reply, revised it once, and it reached you.')
    expect(story?.steps).toEqual([
      "Muse sorted your message first: it doesn't need text from the book, and it asks about things you told Linger before.",
      'Muse asked Serendipity to find something you told Linger before that relates to your message.',
      'Muse drafted a reply, citing 1 earlier chat line and 2 memories: “You read about forty minutes a day.”',
      'It proposed saving “I read on the train.” as a memory, because it is a lasting habit, preference or plan.',
      "Muse rewrote the reply after Provenance's review, with no citations: “You read about forty minutes per round trip.”",
    ])
  })

  it('explains each Provenance verdict with the finding in plain words and its own reason', () => {
    const runs = [
      run('Provenance', 'review', { response_decision: 'revise', capture_decision: 'no_candidate', findings: [FINDING] }),
      run('Provenance', 'review', { response_decision: 'pass', capture_decision: 'allow_capture', findings: [] }),
    ]

    const story = agentStory('provenance', runs, turn())

    expect(story?.summary).toBe('Provenance asked for 1 revision, then passed the reply.')
    expect(story?.steps).toEqual([
      'Provenance checked the draft and sent it back to Muse to fix. The draft asserted something no retrieved evidence supports. Its reason: “The reader never said how many days they ride.”',
      'Provenance checked revision 1 against the evidence and passed it. It allowed the proposed memory to be saved.',
    ])
  })

  it('says a blocked reply was blocked', () => {
    const story = agentStory('provenance', [run('Provenance', 'review', { response_decision: 'reject', findings: [FINDING] })], turn('application_safe_decline'))
    expect(story?.summary).toBe('Provenance blocked the reply.')
  })

  it('tells how far the reader has read and whether the passages were enough', () => {
    const runs = [
      run('Librarian', 'boundary_inference', {
        outcome: 'candidate', work_id: 'pg11', chapter_number: 5, confidence: 0.82, authorization_basis: 'memory_supported',
      }),
      run('Librarian', 'book_request', { parts: [{ purpose: 'answer' }, { purpose: 'reference' }] }),
      run('Librarian', 'evidence_strength', { evidence_strength: 'weak', strength_reason: 'Only one passage mentions the pool.', limitations: ['no later chapters'] }),
    ]

    const story = agentStory('librarian', runs, turn('muse_candidate', 2))

    expect(story?.summary).toBe('Librarian fetched book passages 2 times, staying within the chapters you have read.')
    expect(story?.steps).toEqual([
      "Librarian worked out how far you have read: Alice's Adventures in Wonderland, up to chapter 5 (82% sure, backed by what you told Linger before).",
      'Librarian planned 2 look-ups in the book, to answer your question and find the passage you referred to.',
      'Librarian judged the passages it found too thin to rely on fully: “Only one passage mentions the pool.” Limits it noted: no later chapters.',
    ])
  })

  it('retells a Sculptor proposal and the review that judged it', () => {
    const proposal = run('Sculptor', 'curation', {
      kind: 'curation_proposal',
      action: { action: 'update_derived_summary', source_memory_ids: ['mem_a', 'mem_b'], summary: 'Reads on the train most days.' },
    })
    const review = run('Provenance', 'curation_review', {
      decision: 'reject', findings: [{ code: 'unsupported_summary', source_memory_ids: ['mem_a'], explanation: 'Neither memory says most days' }],
    })

    expect(agentStory('sculptor', [proposal], turn())).toEqual({
      summary: 'Sculptor proposed a change to how your memories are organised for search.',
      steps: ['Sculptor proposed a summary of 2 saved memories: “Reads on the train most days.”'],
    })
    expect(agentStory('curation_review', [review], turn())).toEqual({
      summary: 'Provenance did not allow the memory change as proposed.',
      steps: ["Provenance checked Sculptor's proposal against the saved memories it cites and rejected it. “Neither memory says most days”."],
    })
  })

  it('reports a run that did not finish instead of inventing an outcome', () => {
    const failed: AgentExchange = { ...run('Muse', 'draft', null), status: 'failure', failure_code: 'model_timeout' }
    expect(agentStory('muse', [failed], turn('application_safe_decline'))?.steps).toEqual([
      "Muse's draft run did not finish (model timeout).",
    ])
  })

  it('has nothing to tell without recorded runs', () => {
    expect(agentStory('muse', [], turn())).toBeNull()
  })
})
