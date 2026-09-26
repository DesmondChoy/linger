import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReplyText } from './ReplyText'

describe('ReplyText', () => {
  it('renders emphasis and turns an HTML-wrapped quotation into a quote block', () => {
    const html = renderToStaticMarkup(
      <ReplyText text={'In *The Story of My Life*:\n\n<blockquote>Suddenly I felt a misty\nconsciousness.</blockquote>\n\nWhat stays with you?'} />,
    )
    expect(html).toContain('<em>The Story of My Life</em>')
    expect(html).toMatch(/<blockquote>\s*<p>Suddenly I felt a misty\nconsciousness.<\/p>\s*<\/blockquote>/)
    expect(html).not.toContain('&lt;blockquote')
  })

  it('drops other raw HTML instead of rendering it', () => {
    const html = renderToStaticMarkup(<ReplyText text={'Hi <img src=x onerror=alert(1)> there'} />)
    expect(html).not.toContain('<img')
    expect(html).toContain('Hi')
  })
})
