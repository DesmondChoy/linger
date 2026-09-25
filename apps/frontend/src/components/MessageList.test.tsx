import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Message } from '../types'
import { MessageList } from './MessageList'

describe('MessageList', () => {
  it('shows a persistent AI disclosure regardless of conversation state', () => {
    const html = renderToStaticMarkup(<MessageList messages={[]} pending={false} />)

    expect(html).toContain('Linger is an AI reflection companion and can make mistakes')
    expect(html).toContain('listed under Sources')
  })

  it('shows a Sources footer under a reply that used sources', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: 'Alice keeps changing size in the story.',
        sources: [
          {
            kind: 'book',
            label: "Alice's Adventures in Wonderland",
            location: 'Chapter 5 — Advice from a Caterpillar',
            url: null,
          },
          { kind: 'memory', label: 'Your earlier reflection', location: null, url: null },
        ],
      },
    ]

    const html = renderToStaticMarkup(<MessageList messages={messages} pending={false} />)

    expect(html).toContain('Sources')
    expect(html).toContain('Adventures in Wonderland')
    expect(html).toContain('Chapter 5 — Advice from a Caterpillar')
    expect(html).toContain('Your earlier reflection')
  })

  it('shows no Sources footer for a reply that used none, such as a decline', () => {
    const messages: Message[] = [
      { id: 'a1', role: 'assistant', content: "I can't help with that." },
    ]

    const html = renderToStaticMarkup(<MessageList messages={messages} pending={false} />)

    expect(html).not.toContain('class="sources"')
  })

  it('renders exactly the source labels the backend sent, in order', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: 'reply text',
        sources: [
          { kind: 'book', label: 'Book Title', location: 'Chapter 2 — Something', url: null },
          { kind: 'memory', label: 'Your earlier reflection', location: null, url: null },
        ],
      },
    ]

    const html = renderToStaticMarkup(<MessageList messages={messages} pending={false} />)

    expect(html).toContain('<li>Book Title — Chapter 2 — Something</li>')
    expect(html).toContain('<li>Your earlier reflection</li>')
  })

  it('renders a web source with an http(s) URL as a link', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: 'reply text',
        sources: [
          {
            kind: 'web',
            label: 'https://example.com/article',
            location: null,
            url: 'https://example.com/article',
          },
        ],
      },
    ]

    const html = renderToStaticMarkup(<MessageList messages={messages} pending={false} />)

    expect(html).toContain('<a href="https://example.com/article"')
  })

  it('renders a web source with a non-http(s) URL as plain text, not a link', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: 'reply text',
        sources: [
          {
            kind: 'web',
            label: 'javascript:alert(1)',
            location: null,
            url: 'javascript:alert(1)',
          },
        ],
      },
    ]

    const html = renderToStaticMarkup(<MessageList messages={messages} pending={false} />)

    expect(html).not.toContain('<a ')
    expect(html).toContain('javascript:alert(1)')
  })
})
