export type LibraryUnit = {
  unit_id: string
  chapter_number: number | null
  part_id: string
  part_title: string
  kind: string
  title: string
  label: string
  summary: string
}
export type LibraryBook = {
  work_id: string
  book_version_id: string
  title: string
  author: string
  units: LibraryUnit[]
  start_unit_id: string
}

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseUnit(value: unknown): LibraryUnit {
  if (!isRecord(value) || typeof value.unit_id !== 'string' || !value.unit_id
    || (value.chapter_number !== null && (typeof value.chapter_number !== 'number'
      || !Number.isSafeInteger(value.chapter_number) || value.chapter_number < 1))
    || typeof value.part_id !== 'string' || !value.part_id
    || typeof value.part_title !== 'string' || typeof value.kind !== 'string' || !value.kind
    || typeof value.title !== 'string' || typeof value.label !== 'string' || !value.label
    || typeof value.summary !== 'string') {
    throw new Error('The library returned an invalid reading location.')
  }
  return {
    unit_id: value.unit_id, chapter_number: value.chapter_number,
    part_id: value.part_id, part_title: value.part_title, kind: value.kind,
    title: value.title, label: value.label, summary: value.summary,
  }
}

function parseBook(value: unknown): LibraryBook {
  if (!isRecord(value) || typeof value.work_id !== 'string'
    || typeof value.book_version_id !== 'string' || typeof value.title !== 'string'
    || typeof value.author !== 'string' || !Array.isArray(value.units)
    || value.units.length === 0 || typeof value.start_unit_id !== 'string') {
    throw new Error('The library returned an invalid book.')
  }
  const units = value.units.map(parseUnit)
  if (new Set(units.map((unit) => unit.unit_id)).size !== units.length
    || !units.some((unit) => unit.unit_id === value.start_unit_id)) {
    throw new Error('The library returned inconsistent reading locations.')
  }
  return {
    work_id: value.work_id, book_version_id: value.book_version_id,
    title: value.title, author: value.author, units, start_unit_id: value.start_unit_id,
  }
}

export async function loadLibrary(signal?: AbortSignal): Promise<LibraryBook[]> {
  const response = await fetch(`${BASE_URL}/api/library`, { signal })
  if (!response.ok) throw new Error('Unable to load your library. Check that Linger is running and try again.')
  const payload: unknown = await response.json()
  if (!Array.isArray(payload)) throw new Error('The library returned an invalid book list.')
  return payload.map(parseBook)
}

export async function loadUnit(book: LibraryBook, unit: LibraryUnit, signal?: AbortSignal): Promise<string> {
  const response = await fetch(
    `${BASE_URL}/api/library/${encodeURIComponent(book.work_id)}/${encodeURIComponent(book.book_version_id)}/units/${encodeURIComponent(unit.unit_id)}`,
    { signal },
  )
  if (!response.ok) throw new Error('Unable to open this text. Return to the library or try again.')
  const payload: unknown = await response.json()
  if (!isRecord(payload) || typeof payload.text !== 'string') {
    throw new Error('The library returned invalid reading text.')
  }
  return payload.text
}
