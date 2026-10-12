import { describe, expect, it } from 'vitest'
import { ANY_BOOK, DEMO_BOOKS, DEMO_PATHS, variantsFor } from './demoPrompts'

describe('guided conversation paths', () => {
  it('covers each route a demo needs to show', () => {
    expect(DEMO_PATHS.map((path) => path.id)).toEqual(
      expect.arrayContaining(['spoilers', 'grounded', 'memory', 'web', 'cross-book', 'decline', 'session', 'safety']),
    )
    expect(new Set(DEMO_PATHS.map((path) => path.id)).size).toBe(DEMO_PATHS.length)
  })

  it('gives every path several wordings that each start with something to say', () => {
    for (const path of DEMO_PATHS) {
      expect(path.variants.length, path.id).toBeGreaterThanOrEqual(3)
      for (const variant of path.variants) {
        expect(variant.steps[0].kind, path.id).toBe('line')
        expect(variant.steps.at(-1)?.kind, `${path.id} ends on something to say`).toBe('line')
        variant.steps.forEach((step, index) => {
          expect(step.watch.length, path.id).toBeGreaterThan(0)
          if (step.kind === 'line') expect(step.text.trim().length, path.id).toBeGreaterThan(0)
          else expect(variant.steps[index - 1]?.kind, `${path.id} has no empty new chat`).toBe('line')
        })
      }
    }
  })

  it('keeps wordings of one path the same shape, so a switch keeps your place meaningful', () => {
    for (const path of DEMO_PATHS) {
      const shapes = path.variants.map((variant) => variant.steps.map((step) => step.kind).join(','))
      expect(new Set(shapes).size, path.id).toBeLessThanOrEqual(2)
    }
  })
})

describe('optional book filter', () => {
  it('offers every book on every book-based path', () => {
    for (const path of DEMO_PATHS.filter((item) => item.variants.some((variant) => variant.works?.length))) {
      for (const book of DEMO_BOOKS) {
        expect(variantsFor(path, book.workId).length, `${path.id} × ${book.title}`).toBeGreaterThan(0)
        for (const index of variantsFor(path, book.workId)) {
          expect(path.variants[index].works, `${path.id} × ${book.title}`).toContain(book.workId)
        }
      }
    }
  })

  it('keeps bookless paths available whatever book is chosen, and any-book shows all wordings', () => {
    const session = DEMO_PATHS.find((path) => path.id === 'session')!
    expect(variantsFor(session, 'pg11')).toEqual([0, 1, 2])
    const spoilers = DEMO_PATHS.find((path) => path.id === 'spoilers')!
    expect(variantsFor(spoilers, ANY_BOOK)).toHaveLength(spoilers.variants.length)
  })
})
