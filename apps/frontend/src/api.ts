import type { MemorySaveResult, MemoryState } from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init)
  if (!response.ok) {
    const detail: unknown = await response.json().catch(() => null)
    if (
      typeof detail === 'object' &&
      detail !== null &&
      'detail' in detail &&
      typeof detail.detail === 'string'
    ) {
      throw new Error(detail.detail)
    }
    throw new Error(`Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function sendMessage(
  sessionId: string,
  message: string,
): Promise<string> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${response.status})`)
  }

  const payload: unknown = await response.json()
  if (
    typeof payload !== 'object' ||
    payload === null ||
    !('reply' in payload) ||
    typeof payload.reply !== 'string'
  ) {
    throw new Error('The server returned an invalid response.')
  }
  return payload.reply
}

export async function resetSession(sessionId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
}

export function getMemoryState(): Promise<MemoryState> {
  return requestJson('/api/memories')
}

export function setCapturePreference(enabled: boolean): Promise<{ enabled: boolean }> {
  return requestJson('/api/memory-capture-preference', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
}

export function saveMemory(text: string, operationId: string): Promise<MemorySaveResult> {
  return requestJson('/api/memories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, operation_id: operationId }),
  })
}

export function correctMemory(
  memoryId: string,
  text: string,
  operationId: string,
): Promise<MemorySaveResult> {
  return requestJson(`/api/memories/${encodeURIComponent(memoryId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, operation_id: operationId }),
  })
}

export async function deleteMemory(memoryId: string): Promise<void> {
  const response = await fetch(
    `${BASE_URL}/api/memories/${encodeURIComponent(memoryId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    const detail: unknown = await response.json().catch(() => null)
    if (
      typeof detail === 'object' &&
      detail !== null &&
      'detail' in detail &&
      typeof detail.detail === 'string'
    ) {
      throw new Error(detail.detail)
    }
    throw new Error(`Request failed (${response.status})`)
  }
}
