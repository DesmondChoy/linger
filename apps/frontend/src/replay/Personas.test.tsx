import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import index from './personas/index.json'
import { PersonaGallery } from './PersonaGallery'
import { PersonaReplay } from './PersonaReplay'
import type { Persona, PersonaIndex } from './types'

const data = index as PersonaIndex
const files = import.meta.glob<Persona>(['./personas/*.json', '!./personas/index.json'], { eager: true, import: 'default' })

describe('persona gallery and replay', () => {
  it('groups personas under the catalog menu families', () => {
    const html = renderToStaticMarkup(<PersonaGallery snapshot={data} onOpen={() => {}} onClose={() => {}} closeLabel="Back" />)
    expect(html).toContain('Conversation and memory')
    expect(html).toContain('Retrieval and grounding')
    expect(html).toContain('Helen Keller event-led grounding and clarification')
  })

  it('replays read-only: the recorded feed, answer key and map, with no composer', () => {
    const keller = Object.values(files).find((persona) => persona.id.startsWith('helen-keller'))!
    const html = renderToStaticMarkup(<PersonaReplay persona={keller} onBack={() => {}} onHome={() => {}} />)
    expect(html).toContain('Recorded evaluation · read-only')
    expect(html).toContain('My disappointment was bitter')
    expect(html).toContain('Answer key')
    expect(html).toContain('Sources')
    expect(html).toContain('collaboration-graph')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('>Delete<')
  })
})
