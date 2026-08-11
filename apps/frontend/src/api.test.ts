import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  correctMemory,
  deleteMemory,
  getMemoryState,
  saveMemory,
  setCapturePreference,
} from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('memory API', () => {
  it('loads state and persists the capture preference', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ capture_enabled: false, memories: [] }))
      .mockResolvedValueOnce(jsonResponse({ enabled: true }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getMemoryState()).resolves.toEqual({
      capture_enabled: false,
      memories: [],
    })
    await expect(setCapturePreference(true)).resolves.toEqual({ enabled: true })

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/memories', undefined)
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/memory-capture-preference',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ enabled: true }),
      }),
    )
  })

  it('sends save, correction, and delete operations without account scope', async () => {
    const memory = {
      memory_id: 'mem-1',
      text: 'A memory',
      capture_type: 'explicit',
      evidence_ids: [],
      created_at: '2026-08-11T00:00:00Z',
      updated_at: '2026-08-11T00:00:00Z',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ memory, created: true }, 201))
      .mockResolvedValueOnce(jsonResponse({ memory, created: true }, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await saveMemory('A memory', 'operation-1')
    await correctMemory('mem-1', 'A clearer memory', 'operation-2')
    await deleteMemory('mem-1')

    const saveBody = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    const correctionBody = JSON.parse(fetchMock.mock.calls[1][1].body as string)
    expect(saveBody).toEqual({ text: 'A memory', operation_id: 'operation-1' })
    expect(correctionBody).toEqual({
      text: 'A clearer memory',
      operation_id: 'operation-2',
    })
    expect(saveBody).not.toHaveProperty('account_id')
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/memories/mem-1',
      { method: 'DELETE' },
    )
  })

  it('surfaces server failures without inventing success state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Memory storage is unavailable.' }, 500)),
    )

    await expect(saveMemory('A memory', 'operation-1')).rejects.toThrow(
      'Memory storage is unavailable.',
    )
  })
})
