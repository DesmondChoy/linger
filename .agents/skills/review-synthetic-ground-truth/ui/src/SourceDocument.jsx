import { useId, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const markdownComponents = {
  a: ({ href, children }) => /^https?:\/\//i.test(href ?? '')
    ? <a href={href} rel="noreferrer noopener" target="_blank">{children}</a>
    : <span>{children}</span>,
  img: ({ alt }) => <span className="source-image-description">[Image: {alt || 'no description supplied'}]</span>,
  table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
}

export function MarkdownContent({ text }) {
  return (
    <div className="markdown-content">
      <Markdown components={markdownComponents} remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  )
}

export function publicSourceReadingText(source) {
  const captureHeader = `Title: ${source.title}\nURL: ${source.url}\n\n`
  if (!source.text.startsWith(captureHeader)) return source.text
  const body = source.text.slice(captureHeader.length)
  const pageTitle = `${source.title}\n\n`
  return body.startsWith(pageTitle) ? body.slice(pageTitle.length) : body
}

export function SourceDocument({ text, label, formattedText = text }) {
  const [exact, setExact] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const regionId = useId()
  return (
    <div className="source-document">
      <div className="source-toolbar">
        <div aria-label={`${label} display`} className="source-view-controls" role="group">
          <button aria-pressed={!exact} onClick={() => setExact(false)} type="button">Formatted</button>
          <button aria-pressed={exact} onClick={() => setExact(true)} type="button">Exact text</button>
        </div>
        <button aria-controls={regionId} aria-expanded={expanded} onClick={() => setExpanded(!expanded)} type="button">
          {expanded ? 'Collapse source' : 'Expand source'}
        </button>
      </div>
      <div aria-label={label} className={`source-reading-region ${expanded ? 'is-expanded' : ''}`} id={regionId} role="region" tabIndex={0}>
        {exact ? <pre className="source-exact-text">{text}</pre> : <MarkdownContent text={formattedText} />}
      </div>
    </div>
  )
}
