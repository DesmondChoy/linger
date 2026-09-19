import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkdownContent, publicSourceReadingText, SourceDocument } from './SourceDocument.jsx'

const render = (text) => renderToStaticMarkup(createElement(MarkdownContent, { text }))

describe('source reading view', () => {
  it('removes only matching duplicate capture headings from the formatted view', () => {
    const source = { title: 'Hume', url: 'https://example.com/text', text: 'Title: Hume\nURL: https://example.com/text\n\nHume\n\n#### Of personal identity.\n\nA paragraph.' }
    expect(publicSourceReadingText(source)).toBe('#### Of personal identity.\n\nA paragraph.')
    expect(source.text.startsWith('Title: Hume\nURL: https://example.com/text')).toBe(true)
    const unmatched = { ...source, title: 'Another title' }
    expect(publicSourceReadingText(unmatched)).toBe(unmatched.text)
  })

  it('renders captured headings and separate paragraphs', () => {
    const source = 'Title: Hume Texts Online\nURL: https://davidhume.org/texts/t/1/4/6\n\n#### Of personal identity.\n\nFirst paragraph.\n\nT 1.4.6.2, SBN 251-2\n\nSecond paragraph.'
    const html = render(source)
    expect(html).toContain('<h4>Of personal identity.</h4>')
    expect(html).toContain('<p>First paragraph.</p>')
    expect(html).toContain('<p>T 1.4.6.2, SBN 251-2</p>')
    expect(html).toContain('<p>Second paragraph.</p>')
  })

  it('renders lists, emphasis, tables, and literal code in reports', () => {
    const html = render('**Sources**\n\n- Memory\n- Book\n\n| Source | State |\n| --- | --- |\n| Book | Available |\n\n```text\n<script>literal code</script>\n```')
    expect(html).toContain('<strong>Sources</strong>')
    expect(html).toContain('<li>Memory</li>')
    expect(html).toContain('<table>')
    expect(html).toContain('<td>Available</td>')
    expect(html).toContain('&lt;script&gt;literal code&lt;/script&gt;')
  })

  it('keeps untrusted HTML inert and avoids loading source images or unsafe links', () => {
    const html = render('<script>alert(1)</script>\n\n<img src="https://example.com/tracker">\n\n[unsafe](javascript:alert%281%29) ![diagram](https://example.com/image.png)')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('href="javascript:')
    expect(html).toContain('diagram')
    expect(html).toContain('&lt;script&gt;')
  })

  it('keeps links explicit and prevents relative document paths becoming review API links', () => {
    const html = render('[Public source](https://example.com/text) [local file](../../../docs/specification.md)')
    expect(html).toContain('href="https://example.com/text"')
    expect(html).toContain('rel="noreferrer noopener"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('<span>local file</span>')
  })

  it('exposes the complete source in an accessible reading region with explicit view controls', () => {
    const text = 'Start.\n\n' + 'Long passage.\n\n'.repeat(100) + 'Final source sentence.'
    const html = renderToStaticMarkup(createElement(SourceDocument, { text, label: 'Captured source' }))
    expect(html).toContain('aria-label="Captured source"')
    expect(html).toContain('role="region"')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('Final source sentence.')
    expect(html).toContain('Exact text')
    expect(html).toContain('Expand source')
  })
})
