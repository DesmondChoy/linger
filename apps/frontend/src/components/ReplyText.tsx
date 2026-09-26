import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Muse writes light Markdown; this renders it.
 *
 * Book quotations must match the source character for character, line breaks
 * included, so Muse cannot put Markdown `>` markers inside one and sometimes
 * wraps it in `<blockquote>` tags instead. Those become a quote block here.
 * Any other raw HTML is dropped rather than rendered.
 */
export function ReplyText({ text }: { text: string }) {
  return (
    <div className="reply-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {htmlQuotesToMarkdown(text)}
      </ReactMarkdown>
    </div>
  )
}

function htmlQuotesToMarkdown(text: string): string {
  return text.replace(/<blockquote>\s*([\s\S]*?)\s*<\/blockquote>/gi, (_, quote: string) =>
    `\n\n${quote.split('\n').map((line) => `> ${line.trim()}`).join('\n')}\n\n`)
}
