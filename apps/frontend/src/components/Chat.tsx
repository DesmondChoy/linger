import { useEffect, useRef, useState } from 'react'
import { Icon } from '@linger/architecture-map'
import { ChatRequestError, deleteSession, loadHistory, sendMessage } from '../api'
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

type Props = {
  username: string
  onHome: () => void
  onSignOut: () => void
}

export function Chat({ username, onHome, onSignOut }: Props) {
  // Earlier conversations sit above in the same feed; the newest one continues.
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID())
  const [historyLoaded, setHistoryLoaded] = useState(false)
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

  useEffect(() => {
    loadHistory()
      .then((conversations) => {
        setMessages(conversations.flatMap((conversation) =>
          conversation.turns.flatMap((turn) => [
            {
              id: turn.turn_id,
              role: 'user' as const,
              content: turn.user_message,
              sessionId: conversation.session_id,
              createdAt: turn.created_at,
            },
            {
              id: `${turn.turn_id}-assistant`,
              role: 'assistant' as const,
              content: turn.assistant_message,
              sources: turn.details?.response.sources,
              sessionId: conversation.session_id,
            },
          ])))
        setTimeline(conversations.flatMap((conversation) =>
          conversation.turns.flatMap((turn) => turn.details
            ? [{ ...turn.details.response, progress: turn.details.progress, sessionId: conversation.session_id }]
            : [])))
        const latest = conversations.at(-1)
        if (latest) setSessionId(latest.session_id)
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Could not load earlier chats.')
      })
      .finally(() => setHistoryLoaded(true))
  }, [])

  const conversationHasTurns = messages.some((message) => message.sessionId === sessionId)

  async function handleSend(text: string) {
    const turnId = crypto.randomUUID()
    setMessages((current) => [
      ...current,
      { id: turnId, role: 'user', content: text, sessionId, createdAt: new Date().toISOString() },
      { id: `${turnId}-assistant`, role: 'assistant', content: '', sessionId },
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
      setTimeline((current) => [...current, { ...result, progress: observed, sessionId }])
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

  function clearTurnState() {
    setProgress([])
    setError(null)
    setErrorTrace(null)
    setCaptureNotice(null)
    setPendingMessage(null)
  }

  /** Start a fresh conversation below the earlier ones; the feed keeps them. */
  function handleNewChat() {
    setSessionId(crypto.randomUUID())
    clearTurnState()
  }

  async function handleDeleteConversation(id: string) {
    try {
      await deleteSession(id)
      setMessages((current) => current.filter((message) => message.sessionId !== id))
      setTimeline((current) => current.filter((record) => record.sessionId !== id))
      if (id === sessionId) handleNewChat()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete that conversation.')
    }
  }

  return (
    <main className={`workspace ${libraryOpen ? 'library-open' : ''}`}>
      <section className="chat" aria-label="Reflection chat">
        <header className="chat-header">
          <button
            type="button"
            className="brand brand-home"
            onClick={onHome}
            disabled={pending}
            aria-label="Linger — back to the start page"
          >
            <span aria-hidden="true">L</span>
            <span className="brand-text">
              <span className="brand-name">Linger</span>
              <span className="brand-tagline">Notice what stays with you.</span>
            </span>
          </button>
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
              onClick={handleNewChat}
              disabled={pending || !conversationHasTurns}
            >
              New chat
            </button>
            <button
              className="quiet-button"
              type="button"
              title={`Signed in as ${username}`}
              onClick={onSignOut}
              disabled={pending}
            >
              Sign out
            </button>
          </div>
        </header>

        <MessageList
          messages={messages}
          pending={pending}
          progress={progress[progress.length - 1]}
          onDeleteConversation={handleDeleteConversation}
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
        <Composer ref={composer} disabled={pending || !historyLoaded} onSend={handleSend} />
      </section>

      <section className="analysis" aria-label="How this works">
        {surface === 'live'
          ? <Architecture timeline={timeline} progress={progress} pendingMessage={pendingMessage} />
          : <SavedEvaluation onClose={() => setSurface('live')} />}
      </section>

      {libraryOpen && (
        <div className="library-drawer">
          <Reader disabled={pending} onClose={() => setLibraryOpen(false)} />
        </div>
      )}
    </main>
  )
}
