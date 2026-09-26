import { describe, expect, it } from 'vitest'
import { toBlocks } from './bookText'

describe('toBlocks', () => {
  it('joins hard-wrapped prose into one paragraph per blank-line block', () => {
    const blocks = toBlocks('Down, down, down. There\nwas nothing else to do.\n\nThump! thump!\ndown she came.')
    expect(blocks).toEqual([
      { kind: 'prose', spans: [{ text: 'Down, down, down. There was nothing else to do.', italic: false }] },
      { kind: 'prose', spans: [{ text: 'Thump! thump! down she came.', italic: false }] },
    ])
  })

  it('keeps the lines of indented verse', () => {
    const [verse] = toBlocks('“How doth the little crocodile\n    Improve his shining tail,\nAnd pour the waters of the Nile')
    expect(verse.kind).toBe('verse')
    expect(verse.kind === 'verse' && verse.lines).toHaveLength(3)
  })

  it('marks underscored words as italic', () => {
    const [block] = toBlocks('Ah, _that’s_ the great puzzle!')
    expect(block).toEqual({
      kind: 'prose',
      spans: [
        { text: 'Ah, ', italic: false },
        { text: 'that’s', italic: true },
        { text: ' the great puzzle!', italic: false },
      ],
    })
  })

  it('ignores extra blank lines and Windows line endings', () => {
    expect(toBlocks('\r\nOne\r\ntwo\r\n\r\n\r\n\r\nThree\r\n')).toHaveLength(2)
  })

  it('carries italics across the lines of verse', () => {
    const [verse] = toBlocks('_Alice’s Right Foot,\n      Hearthrug,\n      (with love)._')
    expect(verse).toEqual({
      kind: 'verse',
      lines: [
        [{ text: 'Alice’s Right Foot,', italic: true }],
        [{ text: '      Hearthrug,', italic: true }],
        [{ text: '      (with love).', italic: true }],
      ],
    })
  })
})
