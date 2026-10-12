import { describe, expect, it } from 'vitest'
import { NOT_RECORDED, replayRun } from './adapter'
import type { Persona } from './types'

const files = import.meta.glob<Persona>(['./personas/*.json', '!./personas/index.json'], { eager: true, import: 'default' })
const personas = Object.values(files)
const byPrefix = (prefix: string) => personas.find((persona) => persona.id.startsWith(prefix))!

describe('replaying a recorded run in the live UI shapes', () => {
  it('turns every chat Scene into feed messages and a turn record carrying its answer key', () => {
    const keller = byPrefix('helen-keller')
    const { messages, timeline } = replayRun(keller, keller.runs[0])
    expect(timeline).toHaveLength(keller.runs[0].scenes.length)
    expect(messages).toHaveLength(timeline.length * 2)
    expect(messages[0].dividerLabel).toMatch(/^Scene 1 · keller-grounded · passed$/)
    const first = timeline[0]
    expect(first.inspection.muse_turn.user_message).toContain('Chapter 10')
    expect(first.reply).toContain('My disappointment was bitter')
    expect(first.grading?.status).toBe('passed')
    expect(first.grading?.expected.length).toBeGreaterThan(0)
    expect(first.inspection.context_resolution.chapter_max).toBe(10)
  })

  it('rebuilds a progress stream so the map shows which agents ran', () => {
    const keller = byPrefix('helen-keller')
    const { timeline } = replayRun(keller, keller.runs[0])
    const agents = new Set(timeline[0].progress.map((event) => event.agent))
    expect(agents).toContain('Muse')
    expect(agents).toContain('Provenance')
    expect(timeline[0].progress.every((event, index) => event.sequence === index + 1)).toBe(true)
  })

  it('carries what the run recorded: contract, inputs, lookups and sources', () => {
    const keller = byPrefix('helen-keller')
    const turn = replayRun(keller, keller.runs[0]).timeline[0]
    expect(JSON.parse(turn.inspection.prompt)).toHaveProperty('muse_turn')
    expect(turn.inspection.muse_turn.policy.spoiler_ceiling).toBe(10)
    expect(turn.inspection.dev_trace?.agent_exchanges[0].input_prompt).not.toBe(NOT_RECORDED)
    expect(turn.inspection.librarian_grounding).toHaveLength(1)
    expect(turn.sources).toEqual([expect.objectContaining({ kind: 'book', label: 'The Story of My Life' })])
  })

  it('shows Serendipity search events on connection turns', () => {
    const roses = byPrefix('alice-roses')
    const turn = replayRun(roses, roses.runs[0]).timeline[0]
    const kinds = (turn.inspection.dev_trace?.connection_events ?? []).map((event) => event.kind)
    expect(kinds).toEqual(expect.arrayContaining(['query', 'search', 'discovery']))
  })

  it('shows offline curation as a labelled task with Sculptor on the map', () => {
    const pottery = byPrefix('pottery')
    const { messages, timeline } = replayRun(pottery, pottery.runs[0])
    expect(messages[0].content).toMatch(/^Offline curation task \(no reader message\)/)
    expect(messages[1].content).toMatch(/^Proposed link duplicates over/)
    expect(timeline[0].progress.some((event) => event.agent === 'Sculptor')).toBe(true)
  })

  it('keeps each turn of a multi-turn Scene, with the key on the last one only', () => {
    const continuity = byPrefix('session-continuity')
    const { timeline } = replayRun(continuity, continuity.runs[0])
    const firstScene = timeline.filter((turn) => turn.sessionId?.endsWith('scene-farewell-speech-continuity'))
    expect(firstScene).toHaveLength(4)
    // Each turn keeps its own agent runs rather than all piling onto the last.
    expect(firstScene.every((turn) => turn.progress.length > 0)).toBe(true)
    expect(firstScene.slice(0, 3).every((turn) => turn.grading === undefined)).toBe(true)
    expect(firstScene[3].grading?.status).toBe('ungraded')
  })
})

describe('offline curation on the live map', () => {
  it('draws only the agents that ran, not the chat route', async () => {
    const { buildLiveTurn } = await import('../components/architecture/liveScene')
    const pottery = byPrefix('pottery')
    const turn = replayRun(pottery, pottery.runs[0]).timeline[0]
    const { scene } = buildLiveTurn({ events: turn.progress, userMessage: turn.inspection.muse_turn.user_message, turn })
    const ids = scene.nodes.map((node) => node.id)
    expect(ids).toContain('sculptor')
    expect(ids).not.toContain('muse')
    expect(ids).not.toContain('input')
    expect(scene.summary).toContain('No reader message, nothing released')
  })
})

describe('recorded contracts', () => {
  it('shows the policy Muse actually received', async () => {
    const { componentDetail } = await import('../components/architecture/turnDetail')
    const pigeon = byPrefix('alice-pigeon')
    const turn = replayRun(pigeon, pigeon.runs[0]).timeline.at(-1)!
    const contract = componentDetail('muse', turn).records.find((record) => record.label === 'MuseTurn contract')!
    expect(contract.value).toMatchObject({ policy: { allow_connection: true } })
  })

  it('marks the policy unrecorded only when Muse never drafted', async () => {
    const { museTurnView } = await import('../components/architecture/turnDetail')
    const pottery = byPrefix('pottery')
    const turn = replayRun(pottery, pottery.runs[0]).timeline[0]
    expect(museTurnView(turn)).toMatchObject({ policy: NOT_RECORDED })
  })
})
