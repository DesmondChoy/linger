import { useEffect, useState, type FormEvent } from 'react'
import {
  correctMemory,
  deleteMemory,
  getMemoryState,
  saveMemory,
  setCapturePreference,
} from '../api'
import type { Memory, MemoryState } from '../types'

type Props = {
  onClose: () => void
}

type Notice = {
  text: string
  undoMemoryId?: string
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'The memory action failed.'
}

function memoryDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(
    new Date(value),
  )
}

function replaceMemory(memories: Memory[], previousId: string, next: Memory): Memory[] {
  return memories.map((memory) =>
    memory.memory_id === previousId ? next : memory,
  )
}

function appendMemoryOnce(memories: Memory[], next: Memory): Memory[] {
  return memories.some((memory) => memory.memory_id === next.memory_id)
    ? memories
    : [...memories, next]
}

export function MemoryDrawer({ onClose }: Props) {
  const [memoryState, setMemoryState] = useState<MemoryState | null>(null)
  const [draft, setDraft] = useState('')
  const [draftOperationId, setDraftOperationId] = useState(() => crypto.randomUUID())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [editOperationId, setEditOperationId] = useState(() => crypto.randomUUID())
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>('load')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  useEffect(() => {
    let active = true
    getMemoryState()
      .then((state) => {
        if (active) setMemoryState(state)
      })
      .catch((caught: unknown) => {
        if (active) setError(errorMessage(caught))
      })
      .finally(() => {
        if (active) setBusy(null)
      })
    return () => {
      active = false
    }
  }, [])

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    setBusy('save')
    setError(null)
    try {
      const result = await saveMemory(text, draftOperationId)
      setMemoryState((current) =>
        current
          ? {
              ...current,
              memories: appendMemoryOnce(current.memories, result.memory),
            }
          : current,
      )
      setDraft('')
      setDraftOperationId(crypto.randomUUID())
      setNotice({ text: 'Memory saved.', undoMemoryId: result.memory.memory_id })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  async function handlePreference(enabled: boolean) {
    if (busy) return
    setBusy('preference')
    setError(null)
    try {
      const saved = await setCapturePreference(enabled)
      setMemoryState((current) =>
        current ? { ...current, capture_enabled: saved.enabled } : current,
      )
      setNotice({ text: saved.enabled ? 'Automatic capture enabled.' : 'Automatic capture paused.' })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  async function handleCorrection(event: FormEvent, memoryId: string) {
    event.preventDefault()
    const text = editText.trim()
    if (!text || busy) return
    setBusy(memoryId)
    setError(null)
    try {
      const result = await correctMemory(memoryId, text, editOperationId)
      setMemoryState((current) =>
        current
          ? {
              ...current,
              memories: replaceMemory(current.memories, memoryId, result.memory),
            }
          : current,
      )
      setEditingId(null)
      setEditText('')
      setNotice({ text: 'Memory corrected.' })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  async function handleDelete(memoryId: string) {
    if (busy) return
    setBusy(memoryId)
    setError(null)
    try {
      await deleteMemory(memoryId)
      setMemoryState((current) =>
        current
          ? {
              ...current,
              memories: current.memories.filter(
                (memory) => memory.memory_id !== memoryId,
              ),
            }
          : current,
      )
      setConfirmDeleteId(null)
      setNotice({ text: 'Memory and its history deleted.' })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  async function handleUndo(memoryId: string) {
    if (busy) return
    setBusy('undo')
    setError(null)
    try {
      await deleteMemory(memoryId)
      setMemoryState((current) =>
        current
          ? {
              ...current,
              memories: current.memories.filter(
                (memory) => memory.memory_id !== memoryId,
              ),
            }
          : current,
      )
      setNotice({ text: 'Save undone.' })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(null)
    }
  }

  function beginEdit(memory: Memory) {
    setEditingId(memory.memory_id)
    setEditText(memory.text)
    setEditOperationId(crypto.randomUUID())
    setConfirmDeleteId(null)
    setNotice(null)
  }

  return (
    <aside className="memory-drawer" aria-label="Memory drawer">
      <header className="drawer-header">
        <div>
          <p className="eyebrow">Your archive</p>
          <h2>Memories</h2>
        </div>
        <button
          className="quiet-button"
          type="button"
          onClick={onClose}
          disabled={busy !== null}
        >
          Close
        </button>
      </header>

      <div className="drawer-scroll">
        <section className="capture-setting" aria-labelledby="capture-heading">
          <div>
            <h3 id="capture-heading">Automatic capture</h3>
            <p>This preference will apply when reviewed suggestions become available.</p>
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={memoryState?.capture_enabled ?? false}
              disabled={!memoryState || busy !== null}
              onChange={(event) => void handlePreference(event.target.checked)}
            />
            <span aria-hidden="true" />
            <span className="sr-only">Allow automatic capture</span>
          </label>
        </section>

        <form className="memory-form" onSubmit={handleSave}>
          <label htmlFor="memory-draft">Save something worth returning to</label>
          <textarea
            id="memory-draft"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setDraftOperationId(crypto.randomUUID())
            }}
            placeholder="A thought, detail, or connection…"
            rows={3}
            maxLength={8000}
            disabled={busy !== null}
          />
          <button type="submit" disabled={!draft.trim() || busy !== null}>
            {busy === 'save' ? 'Saving…' : 'Save memory'}
          </button>
        </form>

        <div className="drawer-feedback" aria-live="polite">
          {notice && (
            <p className="notice">
              <span>{notice.text}</span>
              {notice.undoMemoryId && (
                <button
                  type="button"
                  onClick={() => void handleUndo(notice.undoMemoryId!)}
                  disabled={busy !== null}
                >
                  Undo
                </button>
              )}
            </p>
          )}
          {error && <p className="error">{error}</p>}
        </div>

        <section className="memory-library" aria-labelledby="saved-heading">
          <div className="section-heading">
            <h3 id="saved-heading">Saved memories</h3>
            {memoryState && <span>{memoryState.memories.length}</span>}
          </div>

          {busy === 'load' && <p className="drawer-empty">Loading memories…</p>}
          {memoryState?.memories.length === 0 && (
            <p className="drawer-empty">Your archive is empty. Save the first thread above.</p>
          )}

          <div className="memory-list">
            {memoryState?.memories.map((memory) => (
              <article className="memory-card" key={memory.memory_id}>
                {editingId === memory.memory_id ? (
                  <form onSubmit={(event) => void handleCorrection(event, memory.memory_id)}>
                    <label htmlFor={`edit-${memory.memory_id}`}>Correct this memory</label>
                    <textarea
                      id={`edit-${memory.memory_id}`}
                      value={editText}
                      onChange={(event) => {
                        setEditText(event.target.value)
                        setEditOperationId(crypto.randomUUID())
                      }}
                      rows={4}
                      maxLength={8000}
                      disabled={busy !== null}
                      autoFocus
                    />
                    <div className="card-actions">
                      <button type="submit" disabled={!editText.trim() || busy !== null}>
                        Save correction
                      </button>
                      <button
                        className="quiet-button"
                        type="button"
                        onClick={() => setEditingId(null)}
                        disabled={busy !== null}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div className="memory-meta">
                      <span>{memory.capture_type === 'correction' ? 'Corrected' : 'Saved'}</span>
                      <time dateTime={memory.created_at}>{memoryDate(memory.created_at)}</time>
                    </div>
                    <p>{memory.text}</p>
                    {confirmDeleteId === memory.memory_id ? (
                      <div className="delete-confirmation">
                        <span>Delete this memory and its history?</span>
                        <div className="card-actions">
                          <button
                            className="danger-button"
                            type="button"
                            onClick={() => void handleDelete(memory.memory_id)}
                            disabled={busy !== null}
                          >
                            Delete
                          </button>
                          <button
                            className="quiet-button"
                            type="button"
                            onClick={() => setConfirmDeleteId(null)}
                            disabled={busy !== null}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="card-actions">
                        <button
                          className="quiet-button"
                          type="button"
                          onClick={() => beginEdit(memory)}
                          disabled={busy !== null}
                        >
                          Correct
                        </button>
                        <button
                          className="text-button danger-text"
                          type="button"
                          onClick={() => {
                            setConfirmDeleteId(memory.memory_id)
                            setEditingId(null)
                            setNotice(null)
                          }}
                          disabled={busy !== null}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </>
                )}
              </article>
            ))}
          </div>
        </section>
      </div>
    </aside>
  )
}
