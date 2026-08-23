import type { ChatResult, TraceReference } from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export class ChatRequestError extends Error {
  readonly trace?: TraceReference

  constructor(message: string, trace?: TraceReference) {
    super(message)
    this.name = 'ChatRequestError'
    this.trace = trace
  }
}

export async function sendMessage(
  sessionId: string,
  message: string,
  turnId: string,
): Promise<ChatResult> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, turn_id: turnId, message }),
  })
  const payload: unknown = await response.json().catch(() => null)

  if (!response.ok) {
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
  return payload as ChatResult
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
