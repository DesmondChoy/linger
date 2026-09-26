import { afterEach, describe, expect, it, vi } from 'vitest'
import { COVER_TONES, coverTone, savePosition, savedPosition } from './bookshelf'
import type { LibraryBook } from './library'

const book: LibraryBook = {
  work_id: 'pg11',
  book_version_id: 'pg11-v1',
  title: 'Alice',
  author: 'Lewis Carroll',
  start_unit_id: 'ch-1',
  units: ['ch-1', 'ch-2'].map((unit_id, index) => ({
    unit_id, chapter_number: index + 1, part_id: 'main', part_title: 'Main text',
    kind: 'chapter', title: '', label: `Chapter ${index + 1}`, summary: '',
  })),
}

function memoryStorage(): Storage {
  const items = new Map<string, string>()
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => { items.set(key, value) },
    removeItem: (key) => { items.delete(key) },
    clear: () => items.clear(),
    key: () => null,
    get length() { return items.size },
  }
}

describe('bookshelf', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('never repeats a cover colour within one palette run of the shelf', () => {
    const tones = COVER_TONES.map((_, index) => coverTone(index))
    expect(new Set(tones).size).toBe(COVER_TONES.length)
    expect(coverTone(COVER_TONES.length)).toBe(coverTone(0))
  })

  it('remembers the last chapter opened, ignoring ones the book no longer has', () => {
    vi.stubGlobal('localStorage', memoryStorage())
    expect(savedPosition(book)).toBeNull()
    savePosition(book, 'ch-2')
    expect(savedPosition(book)).toBe('ch-2')
    savePosition(book, 'ch-99')
    expect(savedPosition(book)).toBeNull()
  })

  it('reads without storage', () => {
    vi.stubGlobal('localStorage', undefined)
    expect(savedPosition(book)).toBeNull()
    expect(() => savePosition(book, 'ch-1')).not.toThrow()
  })
})
