import { useEffect, useRef } from 'react'
import type { Message, ProgressEvent } from '../types'
import { formatMachineLabel } from './formatMachineLabel'
import { formatSourceLabel } from './sourceLabel'

type Props = { messages: Message[]; pending: boolean; progress?: ProgressEvent }

const HTTP_URL = /^https?:\/\//i

function progressLabel(progress: ProgressEvent | undefined) {
  if (!progress) return 'Starting…'
  const stage = formatMachineLabel(progress.stage).toLowerCase()
  return progress.status === 'running'
    ? `${progress.agent} is working on ${stage}…`
    : `${progress.agent} finished ${stage}.`
}

export function MessageList({ messages, pending, progress }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending, progress])

  return (
    <div className="messages">
      <p className="ai-disclosure">
        Linger is an AI reflection companion and can make mistakes. When a reply draws
        on a book passage, a web page, or your earlier reflections, they’re listed
        under Sources.
      </p>

      {messages.length === 0 && !pending && <p className="empty">Start the conversation below.</p>}

      {messages.map((message, index) =>
        message.role === 'assistant' && message.content === '' ? (
          <div key={index} className="bubble assistant thinking" aria-live="polite">
            <span>{progressLabel(progress)}</span>
            {progress && <small>{(progress.elapsed_ms / 1000).toFixed(1)}s</small>}
          </div>
        ) : (
          <div key={message.id} className={`bubble ${message.role}`}>
            <div>{message.content}</div>
            {message.sources && message.sources.length > 0 && (
              <div className="sources">
                <span className="sources-label">Sources</span>
                <ul>
                  {message.sources.map((source, sourceIndex) => (
                    <li key={sourceIndex}>
                      {source.kind === 'web' && source.url && HTTP_URL.test(source.url) ? (
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {formatSourceLabel(source)}
                        </a>
                      ) : (
                        formatSourceLabel(source)
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ),
      )}

      <div ref={bottomRef} />
    </div>
  )
}
