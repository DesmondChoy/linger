export type LibraryChapter = { number: number; title: string; summary: string }
export type LibraryBook = {
  work_id: string
  book_version_id: string
  title: string
  author: string
  chapters: LibraryChapter[]
}

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseChapter(value: unknown): LibraryChapter {
  if (!isRecord(value) || typeof value.number !== 'number'
    || !Number.isSafeInteger(value.number) || value.number < 1
    || typeof value.title !== 'string' || typeof value.summary !== 'string') {
    throw new Error('The library returned an invalid chapter.')
  }
  return { number: value.number, title: value.title, summary: value.summary }
}

function parseBook(value: unknown): LibraryBook {
  if (!isRecord(value) || typeof value.work_id !== 'string'
    || typeof value.book_version_id !== 'string' || typeof value.title !== 'string'
    || typeof value.author !== 'string' || !Array.isArray(value.chapters)
    || value.chapters.length === 0) {
    throw new Error('The library returned an invalid book.')
  }
  const chapters = value.chapters.map(parseChapter)
  if (new Set(chapters.map((chapter) => chapter.number)).size !== chapters.length) {
    throw new Error('The library returned duplicate chapters.')
  }
  return {
    work_id: value.work_id, book_version_id: value.book_version_id,
    title: value.title, author: value.author, chapters,
  }
}

export async function loadLibrary(signal?: AbortSignal): Promise<LibraryBook[]> {
  const response = await fetch(`${BASE_URL}/api/library`, { signal })
  if (!response.ok) throw new Error('Unable to load your library. Check that Linger is running and try again.')
  const payload: unknown = await response.json()
  if (!Array.isArray(payload)) throw new Error('The library returned an invalid book list.')
  return payload.map(parseBook)
}

export async function loadChapter(book: LibraryBook, chapter: LibraryChapter, signal?: AbortSignal): Promise<string> {
  const response = await fetch(
    `${BASE_URL}/api/library/${encodeURIComponent(book.work_id)}/${encodeURIComponent(book.book_version_id)}/chapters/${chapter.number}`,
    { signal },
  )
  if (!response.ok) throw new Error('Unable to open this chapter. Return to the library or try again.')
  const payload: unknown = await response.json()
  if (!isRecord(payload) || typeof payload.text !== 'string') {
    throw new Error('The library returned invalid chapter text.')
  }
  return payload.text
}
