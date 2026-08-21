import { useEffect, useRef } from 'react'
import type { Message, ProgressEvent } from '../types'

type Props = { messages: Message[]; pending: boolean; progress?: ProgressEvent }

export function MessageList({ messages, pending, progress }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending])

  return (
    <div className="messages">
      {messages.length === 0 && !pending && <p className="empty">Start the conversation below.</p>}

      {messages.map((message, index) =>
        message.role === 'assistant' && message.content === '' ? (
          <div key={index} className="bubble assistant thinking" aria-live="polite">
            <span>{progress?.detail ?? 'Starting…'}</span>
            {progress && <small>{(progress.elapsed_ms / 1000).toFixed(1)}s</small>}
          </div>
        ) : (
          <div key={message.id} className={`bubble ${message.role}`}>
            <div>{message.content}</div>
          </div>
        ),
      )}

      <div ref={bottomRef} />
    </div>
  )
}
