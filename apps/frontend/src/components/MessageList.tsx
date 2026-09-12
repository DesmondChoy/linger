import { useEffect, useRef } from 'react'
import type { Message, ProgressEvent } from '../types'
import { formatMachineLabel } from './formatMachineLabel'

type Props = { messages: Message[]; pending: boolean; progress?: ProgressEvent }

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
          </div>
        ),
      )}

      <div ref={bottomRef} />
    </div>
  )
}
