import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Chat } from './Chat'

/** The single page has to assemble: conversation, tray, composer and map. */
describe('Chat page', () => {
  const html = renderToStaticMarkup(<Chat username="reader" onHome={() => {}} onSignOut={() => {}} />)

  it('shows the conversation and the analysis surface on one page', () => {
    expect(html).toContain('Reflection chat')
    expect(html).toContain('How this works')
    // No turn has run yet, so the map stands by rather than drawing a route.
    expect(html).toContain('No turn to map yet')
  })

  it('offers prompts that fill the composer, and a way into saved evaluations', () => {
    expect(html).toContain('Try a conversation')
    expect(html).toContain('Asks for an exact quote')
    expect(html).toContain('Says where they are')
    // Labels say what the reader is doing, in their words, not ours.
    expect(html).not.toContain('boundary')
    expect(html).toContain('Open a saved evaluation')
  })

  it('keeps the library as a control rather than a permanent column', () => {
    expect(html).toContain('>Library<')
    expect(html).not.toContain('library-drawer')
  })
})
