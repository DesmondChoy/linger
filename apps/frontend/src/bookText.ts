/**
 * Turn plain-text book sources into readable blocks.
 *
 * Project Gutenberg texts hard-wrap prose at about 70 columns, so single line
 * breaks inside a paragraph are joined. Verse keeps its lines: its continuation
 * lines are indented, which prose paragraphs never are. `_word_` marks italics.
 */

export type Span = { text: string, italic: boolean }
export type Block = { kind: 'prose', spans: Span[] } | { kind: 'verse', lines: Span[][] }

export function toBlocks(text: string): Block[] {
  return text
    .replace(/\r\n?/g, '\n')
    .split(/\n\s*\n/)
    .map((block) => block.replace(/^\n+|\s+$/g, ''))
    .filter((block) => block.trim() !== '')
    .map((block): Block => {
      const lines = block.split('\n')
      if (lines.length > 1 && lines.slice(1).some((line) => /^\s{2,}/.test(line))) {
        // Italics can run across verse lines, so the state carries line to line.
        let italic = false
        return {
          kind: 'verse',
          lines: lines.map((line) => {
            const spans = toSpans(line.trimEnd(), italic)
            italic = endsItalic(line, italic)
            return spans
          }),
        }
      }
      return { kind: 'prose', spans: toSpans(lines.map((line) => line.trim()).join(' '), false) }
    })
}

function toSpans(text: string, italic: boolean): Span[] {
  return text
    .split('_')
    .map((part, index) => ({ text: part, italic: index % 2 === 0 ? italic : !italic }))
    .filter((span) => span.text !== '')
}

function endsItalic(text: string, italic: boolean): boolean {
  return (text.split('_').length - 1) % 2 === 1 ? !italic : italic
}
