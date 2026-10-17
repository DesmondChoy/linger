import { describe, expect, it } from 'vitest'
import type { TurnRecord } from '../../types'
import { connectionStory, webStory } from './connectionStory'

const WORDS = { source_kind: 'memory', evidence_id: 'mem_words', excerpt: 'I keep a list of new words I come across and look them up on Sunday afternoons.' }
const UNSETTLED = { source_kind: 'memory', evidence_id: 'mem_unsettled', excerpt: "That chapter left me feeling oddly unsettled and I can't work out why." }
const NOTE = 'Your earlier note about keeping a list of new words is related to language learning.'

/** A recorded memory-recall turn whose reply Provenance rejected. */
function recallTurn(release: Record<string, unknown>, findingCodes: string[] = []): TurnRecord {
  return {
    inspection: {
      release: { finding_codes: findingCodes },
      dev_trace: {
        agent_exchanges: [{
          role: 'Serendipity', stage: 'memory_recall', skill: 'serendipity.memory-recall', status: 'success',
          input_prompt: JSON.stringify({ intent: 'recall_memory', scope: { allowed_sources: ['memory'] } }),
        }],
        connection_events: [
          { kind: 'search', status: 'evidence_found', operation: 'search_memories', source: 'memory', evidence: [WORDS] },
          { kind: 'search', status: 'evidence_found', operation: 'search_memories', source: 'memory', evidence: [WORDS, UNSETTLED] },
          { kind: 'discovery', status: 'recall', evidence: [WORDS, UNSETTLED], decision: { status: 'recall', evidence_ids: ['mem_words'], relevance_note: NOTE } },
          { kind: 'release', ...release },
        ],
      },
    },
  } as unknown as TurnRecord
}

describe('connectionStory', () => {
  it('retells a rejected memory recall as plain steps', () => {
    const story = connectionStory(recallTurn(
      { status: 'declined', release_source: 'application_safe_decline', provenance_verdicts: ['reject'] },
      ['unsupported_claim'],
    ))

    expect(story?.summary).toBe('Serendipity found something, but Provenance blocked the reply built on it.')
    expect(story?.steps).toEqual([
      'Linger asked Serendipity to find something you told Linger before that relates to your message. It was allowed to look only in your saved memories.',
      `Search 1 of your saved memories found 1 new memory: “${WORDS.excerpt}”`,
      `Search 2 of your saved memories found 1 new memory: “${UNSETTLED.excerpt}” (plus 1 already found).`,
      `Serendipity picked 1 of the 2 it found: “${WORDS.excerpt}” Its own note: “${NOTE}”`,
      'Muse wrote a reply using it, but Provenance rejected that reply, so Linger sent a fixed decline message instead. The draft asserted something no retrieved evidence supports. Open Provenance for its full review.',
    ])
  })

  it('says when the reply built on the pick reached the reader', () => {
    const story = connectionStory(recallTurn(
      { status: 'released', release_source: 'muse_candidate', provenance_verdicts: ['pass'], released_evidence_ids: ['mem_words'] },
    ))

    expect(story?.summary).toBe('Serendipity found something, and the reply built on it reached you.')
    expect(story?.steps.at(-1)).toBe('Muse wrote the reply around it, Provenance checked it, and you saw that reply.')
  })

  it('explains a decline in words, not a reason code', () => {
    const turn = recallTurn({ status: 'declined', release_source: 'muse_candidate' })
    turn.inspection.dev_trace!.connection_events = [
      { kind: 'search', status: 'no_evidence', operation: 'search_memories', source: 'memory' },
      { kind: 'discovery', status: 'decline', decision: { status: 'decline', reason: 'no_matching_memory' } },
    ]

    const story = connectionStory(turn)

    expect(story?.summary).toBe('Serendipity offered nothing.')
    expect(story?.steps.slice(1)).toEqual([
      'Search 1 of your saved memories found nothing relevant.',
      'Serendipity decided not to offer anything, because none of your saved memories matched.',
    ])
  })

  it('names opened pages by title instead of retelling their fetch', () => {
    const turn = recallTurn({ status: 'released', release_source: 'muse_candidate' })
    turn.inspection.dev_trace!.connection_events = [
      { kind: 'query', status: 'sent', source: 'web', operation: 'web_search', query: 'art that expresses feelings' },
      { kind: 'search', status: 'evidence_found', source: 'web', operation: 'web_search' },
      { kind: 'query', status: 'sent', source: 'web', operation: 'get_page', query: 'https://example.org/scream' },
      { kind: 'search', status: 'evidence_found', source: 'web', operation: 'get_page', evidence: [{ evidence_id: 'https://example.org/scream', excerpt: 'Title: The Scream\nURL: https://example.org/scream\n\nBody' }] },
    ]

    expect(connectionStory(turn)?.steps.slice(1)).toEqual([
      'Searched the web for “art that expresses feelings”.',
      'The web search returned pages worth opening.',
      'Read the page “The Scream”.',
    ])
  })

  it('stays silent when Serendipity never ran and only the release was recorded', () => {
    const turn = recallTurn({ status: 'released', release_source: 'muse_candidate' })
    turn.inspection.dev_trace!.connection_events = [{ kind: 'release', status: 'released', release_source: 'muse_candidate' }]
    expect(connectionStory(turn)).toBeNull()
  })

  it('has nothing to tell without the developer trace', () => {
    const turn = recallTurn({})
    turn.inspection.dev_trace = null
    expect(connectionStory(turn)).toBeNull()
  })
})

describe('webStory', () => {
  const SCREAM = { evidence_id: 'https://example.org/scream', excerpt: 'Title: The Scream\nURL: https://example.org/scream' }
  const DEGAS = { evidence_id: 'https://example.org/degas', excerpt: 'Title: Young Woman\nURL: https://example.org/degas' }

  function webTurn(release: Record<string, unknown>): TurnRecord {
    const turn = recallTurn(release)
    turn.inspection.dev_trace!.connection_events = [
      { kind: 'query', status: 'sent', source: 'web', operation: 'web_search', query: 'art that expresses feelings' },
      { kind: 'query', status: 'blocked', source: 'web', operation: 'web_search', query: 'my sister' },
      { kind: 'search', status: 'evidence_found', source: 'web', operation: 'web_search' },
      { kind: 'search', status: 'evidence_found', source: 'web', operation: 'get_page', evidence: [SCREAM] },
      { kind: 'search', status: 'evidence_found', source: 'web', operation: 'get_page', evidence: [DEGAS] },
      { kind: 'discovery', status: 'proposal', evidence: [SCREAM, DEGAS], decision: {} },
      { kind: 'release', ...release },
    ]
    return turn
  }

  it('shows what was searched, what was read and which pages the reply cited', () => {
    const story = webStory(webTurn({ status: 'released', release_source: 'muse_candidate', released_evidence_ids: [SCREAM.evidence_id] }))

    expect(story).toEqual({
      summary: 'Serendipity searched the web once and read 2 pages; the reply cited 1. One search was blocked for privacy.',
      steps: [
        'Searched the web for “art that expresses feelings”.',
        'A web search was blocked because it would have sent your private details.',
        'The web search returned pages worth opening.',
        'Read the page “The Scream”.',
        'Read the page “Young Woman”.',
        'The reply that reached you cited “The Scream”.',
      ],
    })
  })

  it('says when the reply built on the pages was blocked', () => {
    const story = webStory(webTurn({ status: 'declined', release_source: 'application_safe_decline', provenance_verdicts: ['reject'] }))
    expect(story?.steps.at(-1)).toBe('The reply built on these pages did not reach you.')
  })

  it('has nothing to tell when the web was not used', () => {
    expect(webStory(recallTurn({ status: 'released', release_source: 'muse_candidate' }))).toBeNull()
  })
})
