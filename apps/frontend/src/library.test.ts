import { afterEach, expect, it, vi } from 'vitest'
import { loadChapter, loadLibrary } from './library'
import type { LibraryBook } from './library'

const animalFarm: LibraryBook = {
  work_id: 'pga0100011', book_version_id: 'pga0100011-vc7ff4da7', title: 'Animal Farm', author: 'George Orwell',
  chapters: [{ number: 1, title: 'Chapter I', summary: 'Old Major addresses the animals.' }],
}
function respond(value: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(value), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
afterEach(() => vi.unstubAllGlobals())

it('loads the server shelf, including an empty grant, without adding hard-coded books', async () => {
  respond([animalFarm])
  await expect(loadLibrary()).resolves.toEqual([animalFarm])
  respond([])
  await expect(loadLibrary()).resolves.toEqual([])
})

it('requests the selected exact revision and chapter with cancellation', async () => {
  const fetchMock = respond({ text: 'The animals gathered in the barn.' })
  const controller = new AbortController()
  await expect(loadChapter(animalFarm, { number: 2, title: 'Chapter II', summary: '' }, controller.signal))
    .resolves.toBe('The animals gathered in the barn.')
  expect(fetchMock).toHaveBeenCalledWith('/api/library/pga0100011/pga0100011-vc7ff4da7/chapters/2', { signal: controller.signal })
})

it.each([
  {}, [{ ...animalFarm, chapters: [] }],
  [{ ...animalFarm, chapters: [{ number: '1', title: 'Chapter I', summary: '' }] }],
  [{ ...animalFarm, chapters: [...animalFarm.chapters, ...animalFarm.chapters] }],
])('rejects invalid library data before rendering it', async (payload) => {
  respond(payload)
  await expect(loadLibrary()).rejects.toThrow(/library returned/)
})

it('reports unavailable books and invalid chapter responses', async () => {
  respond({ detail: 'Not found' }, 404)
  await expect(loadChapter(animalFarm, { number: 1, title: 'Chapter I', summary: '' })).rejects.toThrow('Unable to open')
  respond({ text: 42 })
  await expect(loadChapter(animalFarm, { number: 1, title: 'Chapter I', summary: '' })).rejects.toThrow('invalid chapter text')
  respond({}, 503)
  await expect(loadLibrary()).rejects.toThrow('Unable to load')
})
