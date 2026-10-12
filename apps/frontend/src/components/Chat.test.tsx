import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Chat } from './Chat'

/** The single page has to assemble: conversation, tray, composer and map. */
describe('Chat page', () => {
  const html = renderToStaticMarkup(<Chat username="reader" onHome={() => {}} onSignOut={() => {}} onOpenPersonas={() => {}} />)

  it('shows the conversation and the analysis surface on one page', () => {
    expect(html).toContain('Reflection chat')
    expect(html).toContain('How this works')
    // No turn has run yet, so the map stands by rather than drawing a route.
    expect(html).toContain('No turn to map yet')
  })

  it('offers guided paths that fill the composer, and a way into persona replays', () => {
    expect(html).toContain('Try a conversation')
    expect(html).toContain('Keeping spoilers out')
    expect(html).toContain('Remembering you')
    // Labels say what the reader is doing, in their words, not ours.
    expect(html).not.toContain('boundary')
    expect(html).toContain('Replay a synthetic persona')
  })

  it('keeps the library as a control rather than a permanent column', () => {
    expect(html).toContain('>Library<')
    expect(html).not.toContain('library-drawer')
  })
})
