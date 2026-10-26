import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import index from './scenarios/index.json'
import { ScenarioGallery } from './ScenarioGallery'
import { ScenarioReplay } from './ScenarioReplay'
import type { Scenario, ScenarioIndex } from './types'

const data = index as ScenarioIndex
const files = import.meta.glob<Scenario>(['./scenarios/*.json', '!./scenarios/index.json'], { eager: true, import: 'default' })

describe('scenario gallery and replay', () => {
  it('groups scenarios under the catalog menu families', () => {
    const html = renderToStaticMarkup(<ScenarioGallery snapshot={data} onOpen={() => {}} onClose={() => {}} closeLabel="Back" />)
    expect(html).toContain('Conversation and memory')
    expect(html).toContain('Retrieval and grounding')
    expect(html).toContain('Helen Keller event-led grounding and clarification')
  })

  it('replays read-only: the recorded feed, answer key and map, with no composer', () => {
    const keller = Object.values(files).find((scenario) => scenario.id.startsWith('helen-keller'))!
    const html = renderToStaticMarkup(<ScenarioReplay scenario={keller} onBack={() => {}} onHome={() => {}} signedIn={false} onOpenLive={() => {}} />)
    expect(html).toContain('Recorded evaluation · read-only')
    expect(html).toContain('My disappointment was bitter')
    expect(html).toContain('Answer key')
    expect(html).toContain('Sources')
    expect(html).toContain('collaboration-graph')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('>Delete<')
    expect(html).toContain('Reading progress')
  })

  it('offers to load the Props only to a signed-in reader', () => {
    const pottery = Object.values(files).find((scenario) => scenario.id.startsWith('pottery'))!
    const render = (signedIn: boolean) => renderToStaticMarkup(
      <ScenarioReplay scenario={pottery} onBack={() => {}} onHome={() => {}} signedIn={signedIn} onOpenLive={() => {}} />,
    )
    expect(render(true)).toContain(`Load these ${pottery.props.length} memories into my account`)
    expect(render(false)).not.toContain('Load these')
    expect(render(false)).toContain('Sign in to load these memories')
  })
})
