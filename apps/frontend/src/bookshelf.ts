import type { LibraryBook } from './library'

/** Cover colours: deep enough for white type, distinct side by side on a shelf. */
export const COVER_TONES = ['#4d5796', '#7a3b4f', '#2f6b5e', '#8a5a2b', '#3d5a80', '#5b4b8a', '#6b705c']

/** Cover colour by shelf position, so neighbouring books never share one. */
export function coverTone(shelfIndex: number): string {
  return COVER_TONES[shelfIndex % COVER_TONES.length]
}

const positionKey = (book: LibraryBook) => `linger.reading.${book.book_version_id}`

/** The chapter this browser last opened in a book, if it still exists. */
export function savedPosition(book: LibraryBook): string | null {
  try {
    const unitId = localStorage.getItem(positionKey(book))
    return unitId && book.units.some((unit) => unit.unit_id === unitId) ? unitId : null
  } catch {
    return null
  }
}

export function savePosition(book: LibraryBook, unitId: string) {
  try {
    localStorage.setItem(positionKey(book), unitId)
  } catch {
    // Storage can be unavailable (private mode); reading still works without it.
  }
}
