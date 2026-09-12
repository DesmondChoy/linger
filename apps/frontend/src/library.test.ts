import { afterEach, expect, it, vi } from 'vitest'
import { loadUnit, loadLibrary } from './library'
import type { LibraryBook, LibraryUnit } from './library'

const chapter: LibraryUnit = {
  unit_id: 'pg2397-vb3cc1e13-sec003', chapter_number: 1, part_id: 'main',
  part_title: 'Part I: Autobiography', kind: 'chapter', title: 'CHAPTER I',
  label: 'Part I, Chapter 1', summary: 'Helen recounts her childhood.',
}
const letter: LibraryUnit = {
  ...chapter, unit_id: 'pg2397-vb3cc1e13-sec027', chapter_number: null,
  part_id: 'letters', part_title: 'Part II: Letters', kind: 'letter',
  title: 'To Miss Anne Sullivan', label: 'To Miss Anne Sullivan — August 20, 1887', summary: '',
}
const keller: LibraryBook = {
  work_id: 'pg2397', book_version_id: 'pg2397-vb3cc1e13', title: 'The Story of My Life', author: 'Helen Keller',
  units: [chapter, letter, { ...chapter, unit_id: 'pg2397-vb3cc1e13-sec136', part_id: 'part-iii', part_title: 'Part III', label: 'Part III, Chapter 1' }],
  start_unit_id: chapter.unit_id,
}
function respond(value: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(value), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
afterEach(() => vi.unstubAllGlobals())

it('loads named letters and repeated chapter numbers in separate parts, including an empty grant', async () => {
  respond([keller])
  await expect(loadLibrary()).resolves.toEqual([keller])
  respond([])
  await expect(loadLibrary()).resolves.toEqual([])
})

it('requests the selected stable reading location and exact revision with cancellation', async () => {
  const fetchMock = respond({ text: 'My dear teacher.' })
  const controller = new AbortController()
  await expect(loadUnit(keller, letter, controller.signal)).resolves.toBe('My dear teacher.')
  expect(fetchMock).toHaveBeenCalledWith('/api/library/pg2397/pg2397-vb3cc1e13/units/pg2397-vb3cc1e13-sec027', { signal: controller.signal })
})

it.each([
  {}, [{ ...keller, units: [] }],
  [{ ...keller, units: [{ ...chapter, chapter_number: '1' }] }],
  [{ ...keller, units: [...keller.units, chapter] }],
  [{ ...keller, start_unit_id: 'missing' }],
  [{ ...keller, units: [{ ...chapter, part_id: null }] }],
])('rejects invalid library data before rendering it', async (payload) => {
  respond(payload)
  await expect(loadLibrary()).rejects.toThrow(/library returned/)
})

it('reports unavailable books and invalid text responses', async () => {
  respond({ detail: 'Not found' }, 404)
  await expect(loadUnit(keller, letter)).rejects.toThrow('Unable to open')
  respond({ text: 42 })
  await expect(loadUnit(keller, letter)).rejects.toThrow('invalid reading text')
  respond({}, 503)
  await expect(loadLibrary()).rejects.toThrow('Unable to load')
})
