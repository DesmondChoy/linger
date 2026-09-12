import type { ChatResult, ProgressEvent, TraceReference } from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export class ChatRequestError extends Error {
  readonly trace?: TraceReference

  constructor(message: string, trace?: TraceReference) {
    super(message)
    this.name = 'ChatRequestError'
    this.trace = trace
  }
}

const PROGRESS_STATUSES = ['running', 'complete', 'declined', 'failed']

/**
 * Run one turn over the progress stream.
 *
 * The server emits content-free `progress` frames while the agents work, then
 * exactly one `result` or `error` frame carrying the same atomic contract the
 * non-streaming endpoint returns.
 */
export async function sendMessage(
  sessionId: string,
  message: string,
  turnId: string,
  onProgress: (event: ProgressEvent) => void,
): Promise<ChatResult> {
  const response = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, turn_id: turnId, message }),
  })

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const detail = isRecord(payload) ? payload.detail : undefined
    throw new ChatRequestError(
      isRecord(detail) && typeof detail.message === 'string'
        ? detail.message
        : typeof detail === 'string'
          ? detail
          : `Request failed (${response.status})`,
      isRecord(detail) && isTraceReference(detail.trace) ? detail.trace : undefined,
    )
  }
  if (!response.body) {
    throw new ChatRequestError('The server did not provide a progress stream.')
  }

  let result: ChatResult | null = null
  let failure: ChatRequestError | null = null

  function consumeFrame(frame: string) {
    if (!frame.trim() || frame.trimStart().startsWith(':')) return
    let eventName = 'message'
    const data: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length) return

    let payload: unknown
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      throw new ChatRequestError('The server returned an invalid progress event.')
    }

    if (eventName === 'progress') {
      if (!isProgressEvent(payload)) {
        throw new ChatRequestError('The server returned invalid progress metadata.')
      }
      onProgress(payload)
    } else if (eventName === 'result') {
      result = payload as ChatResult
    } else if (eventName === 'error') {
      const detail = isRecord(payload) ? payload : {}
      failure = new ChatRequestError(
        typeof detail.detail === 'string' ? detail.detail : 'The request failed.',
        isTraceReference(detail.trace) ? detail.trace : undefined,
      )
    }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) consumeFrame(frame)
    if (done) break
  }
  if (buffer.trim()) consumeFrame(buffer)

  if (failure) throw failure
  if (!result) {
    throw new ChatRequestError('The progress stream ended before a reply arrived.')
  }
  return result
}

function isProgressEvent(value: unknown): value is ProgressEvent {
  return isRecord(value)
    && typeof value.sequence === 'number'
    && typeof value.elapsed_ms === 'number'
    && typeof value.agent === 'string'
    && typeof value.stage === 'string'
    && typeof value.detail === 'string'
    && typeof value.input_origin === 'string'
    && typeof value.output_receiver === 'string'
    && PROGRESS_STATUSES.includes(String(value.status))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isTraceReference(value: unknown): value is TraceReference {
  return isRecord(value)
    && /^[0-9a-f]{32}$/.test(String(value.trace_id))
}

export async function resetSession(sessionId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`Reset failed (${response.status})`)
  }
}
