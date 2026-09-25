import { useRef, useState } from 'react'
import { Icon } from '@linger/architecture-map'
import { ChatRequestError, resetSession, sendMessage } from '../api'
import type {
  MemoryCaptureNotice,
  Message,
  ProgressEvent,
  TraceReference,
  TurnRecord,
} from '../types'
import { Architecture } from './architecture/Architecture'
import { SavedEvaluation } from './architecture/SavedEvaluation'
import { Composer, type ComposerHandle } from './Composer'
import { InputTray } from './InputTray'
import { MessageList } from './MessageList'
import { Reader } from './Reader'
import { playableScenarios } from '@linger/architecture-map'

type Surface = 'live' | 'evaluation'

export function Chat() {
  // One session per page load. Reloading starts a fresh conversation.
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<Message[]>([])
  const [timeline, setTimeline] = useState<TurnRecord[]>([])
  const [surface, setSurface] = useState<Surface>('live')
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [progress, setProgress] = useState<ProgressEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [errorTrace, setErrorTrace] = useState<TraceReference | null>(null)
  const [captureNotice, setCaptureNotice] = useState<MemoryCaptureNotice | null>(null)
  const [pendingMessage, setPendingMessage] = useState<string | null>(null)
  const composer = useRef<ComposerHandle>(null)

  async function handleSend(text: string) {
    const turnId = crypto.randomUUID()
    setMessages((current) => [
      ...current,
      { id: turnId, role: 'user', content: text },
      { id: `${turnId}-assistant`, role: 'assistant', content: '' },
    ])
    setPending(true)
    setPendingMessage(text)
    setError(null)
    setErrorTrace(null)
    setProgress([])

    // Collected locally as well as in state so the finished turn keeps every
    // event even if the last render has not flushed yet.
    const observed: ProgressEvent[] = []

    try {
      const result = await sendMessage(sessionId, text, turnId, (event) => {
        observed.push(event)
        setProgress((current) => [...current, event])
      })
      setMessages((current) => [
        ...current.slice(0, -1),
        { ...current[current.length - 1], content: result.reply, sources: result.sources },
      ])
      setTimeline((current) => [...current, { ...result, progress: observed }])
      setCaptureNotice(result.memory_capture)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
      setErrorTrace(caught instanceof ChatRequestError ? caught.trace ?? null : null)
      // The server stores nothing on a failed request, so roll back both local
      // messages and keep the two histories aligned.
      setMessages((current) => current.slice(0, -2))
    } finally {
      setPending(false)
      setPendingMessage(null)
    }
  }

  async function handleReset() {
    await resetSession(sessionId)
    setSessionId(crypto.randomUUID())
    setMessages([])
    setTimeline([])
    setProgress([])
    setError(null)
    setErrorTrace(null)
    setCaptureNotice(null)
    setPendingMessage(null)
  }

  return (
    <main className={`workspace ${libraryOpen ? 'library-open' : ''}`}>
      <section className="chat" aria-label="Reflection chat">
        <header className="chat-header">
          <div className="brand">
            <span aria-hidden="true">L</span>
            <div>
              <h1>Linger</h1>
              <p>Notice what stays with you.</p>
            </div>
          </div>
          <div className="header-actions">
            <button
              className="quiet-button icon-label"
              type="button"
              aria-pressed={libraryOpen}
              onClick={() => setLibraryOpen((value) => !value)}
            >
              <Icon name="librarian" size={15} />
              Library
            </button>
            <button
              className="quiet-button"
              type="button"
              onClick={handleReset}
              disabled={pending || !messages.length}
            >
              New chat
            </button>
          </div>
        </header>

        <MessageList
          messages={messages}
          pending={pending}
          progress={progress[progress.length - 1]}
        />
        {captureNotice && (
          <p className="notice">
            <span>{captureNotice.notice}</span>
          </p>
        )}
        {error && (
          <p className="error">
            {error}
            {errorTrace && <> Reference: <code>{errorTrace.trace_id}</code></>}
          </p>
        )}

        <InputTray
          disabled={pending}
          onFill={(text) => composer.current?.fill(text)}
          onOpenEvaluations={() => setSurface('evaluation')}
          evaluationCount={playableScenarios.reduce((total, item) => total + item.runs.length, 0)}
        />
        <Composer ref={composer} disabled={pending} onSend={handleSend} />
      </section>

      <section className="analysis" aria-label="How this works">
        {surface === 'live'
          ? <Architecture timeline={timeline} progress={progress} pendingMessage={pendingMessage} />
          : <SavedEvaluation onClose={() => setSurface('live')} />}
      </section>

      {libraryOpen && (
        <div className="library-drawer">
          <Reader disabled={pending} />
        </div>
      )}
    </main>
  )
}
