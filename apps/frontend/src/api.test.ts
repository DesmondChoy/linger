import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatRequestError, resetSession, sendMessage } from './api'
import type { ProgressEvent } from './types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Build an SSE body, optionally split across chunks to exercise buffering. */
function sseResponse(frames: [string, unknown][], chunkSize?: number): Response {
  const body = frames
    .map(([event, data]) => (
      // A leading colon marks a server keep-alive comment rather than an event.
      event.startsWith(':')
        ? `${event}\n\n`
        : `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
    ))
    .join('')
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const size = chunkSize ?? body.length
      for (let index = 0; index < body.length; index += size) {
        controller.enqueue(encoder.encode(body.slice(index, index + size)))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

const progressEvent: ProgressEvent = {
  sequence: 1,
  elapsed_ms: 1200,
  agent: 'Muse',
  stage: 'draft',
  status: 'running',
  detail: 'Muse candidate generation is in progress.',
  input_origin: 'Application',
  output_receiver: 'Application',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('chat API', () => {
  it('sends one Muse message and retains server trace correlation', async () => {
    const payload = {
      reply: 'A reflection',
      inspection: {
        muse_turn: {
          turn_id: 'turn-1',
          user_message: 'What stayed with me?',
          reading_context: null,
          policy: {
            spoiler_ceiling: null,
            allow_retrieval: false,
            allow_connection: false,
            allow_memory_capture: false,
          },
        },
        context_resolution: {
          status: 'unknown',
          work_id: null,
          work_title: null,
          chapter_max: null,
          boundary_source: null,
          explanation: 'No book context.',
        },
        traces: [],
        connection_decline: null,
        librarian_grounding: [],
        prompt: '{}',
        release: null,
      },
      trace: {
        trace_id: '01979d1e4e4325335569dba4459473fc',
      },
      memory_capture: null,
    }
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([['progress', progressEvent], ['result', payload]]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const observed: ProgressEvent[] = []

    await expect(
      sendMessage('session-1', 'What stayed with me?', 'turn-1', (event) => observed.push(event)),
    ).resolves.toEqual(payload)
    expect(observed).toEqual([progressEvent])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/stream',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          session_id: 'session-1',
          turn_id: 'turn-1',
          message: 'What stayed with me?',
        }),
      }),
    )
  })

  it('reassembles progress frames split across stream chunks', async () => {
    const second = { ...progressEvent, sequence: 2, elapsed_ms: 2400, status: 'complete' as const }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      sseResponse(
        [
          ['progress', progressEvent],
          [':keep-alive', {}],
          ['progress', second],
          ['result', { reply: 'A reflection' }],
        ],
        7,
      ),
    ))
    const observed: ProgressEvent[] = []

    const result = await sendMessage('session-1', 'Hello', 'turn-1', (event) => observed.push(event))

    expect(observed).toEqual([progressEvent, second])
    expect(result.reply).toBe('A reflection')
  })

  it('surfaces a streamed failure with its safe trace correlation', async () => {
    const trace = { trace_id: '01979d1e4e4325335569dba4459473fc' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      sseResponse([
        ['progress', progressEvent],
        ['error', { detail: 'The model call failed. Try again.', trace }],
      ]),
    ))

    await expect(
      sendMessage('session-1', 'Hello', 'turn-1', () => {}),
    ).rejects.toMatchObject({
      name: 'ChatRequestError',
      message: 'The model call failed. Try again.',
      trace,
    } satisfies Partial<ChatRequestError>)
  })

  it('retains safe trace correlation when the request never opens a stream', async () => {
    const trace = { trace_id: '01979d1e4e4325335569dba4459473fc' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      detail: { message: 'The model call failed. Try again.', trace },
    }, 502)))

    await expect(
      sendMessage('session-1', 'Hello', 'turn-1', () => {}),
    ).rejects.toMatchObject({
      name: 'ChatRequestError',
      message: 'The model call failed. Try again.',
      trace,
    } satisfies Partial<ChatRequestError>)
  })

  it('fails when the stream ends without a reply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      sseResponse([['progress', progressEvent]]),
    ))

    await expect(
      sendMessage('session-1', 'Hello', 'turn-1', () => {}),
    ).rejects.toThrow('The progress stream ended before a reply arrived.')
  })
})

describe('session API', () => {
  it('resets only the selected conversation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await resetSession('session / 1')

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session%20%2F%201', { method: 'DELETE' })
  })
})
