import { useState } from 'react'
import { Icon } from '@linger/architecture-map'
import { DEMO_BOOKS } from './demoPrompts'

type Props = {
  disabled: boolean
  /** Fills the composer with editable text. Never sends. */
  onFill: (text: string) => void
  onOpenEvaluations: () => void
  evaluationCount: number
}

/**
 * Two ways in, kept visually distinct because they make different claims.
 *
 * A prompt is a line you could have typed: live, and nothing checks it. A saved
 * evaluation is an archived run with an answer key a person adopted. Collapsing
 * them into one list would imply the first has ground truth behind it.
 */
export function InputTray({ disabled, onFill, onOpenEvaluations, evaluationCount }: Props) {
  const [workId, setWorkId] = useState(DEMO_BOOKS[0].workId)
  const [used, setUsed] = useState<Set<string>>(new Set())
  const [previewed, setPreviewed] = useState<string | null>(null)
  const book = DEMO_BOOKS.find((item) => item.workId === workId) ?? DEMO_BOOKS[0]

  return (
    <div className="input-tray">
      <div className="tray-head">
        <p className="eyebrow">Try a conversation</p>
        <label className="tray-book">
          <span className="visually-hidden">Book</span>
          <select
            value={workId}
            onChange={(event) => { setWorkId(event.target.value); setUsed(new Set()) }}
            disabled={disabled}
          >
            {DEMO_BOOKS.map((item) => (
              <option key={item.workId} value={item.workId}>{item.title}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="tray-chips">
        {book.lines.map((line) => (
          <button
            key={line.label}
            type="button"
            className={`tray-chip${used.has(line.label) ? ' is-used' : ''}`}
            disabled={disabled}
            title={line.text}
            onMouseEnter={() => setPreviewed(line.label)}
            onMouseLeave={() => setPreviewed(null)}
            onFocus={() => setPreviewed(line.label)}
            onBlur={() => setPreviewed(null)}
            onClick={() => {
              onFill(line.text)
              setUsed((current) => new Set(current).add(line.label))
            }}
          >
            {used.has(line.label) && <span aria-hidden="true">✓</span>}
            {line.label}
          </button>
        ))}
      </div>

      <p className="tray-watch" aria-live="polite">
        {book.lines.find((line) => line.label === previewed)?.watch
          ?? 'Pick lines in any order, or type your own, to build up one conversation. Each fills the box; nothing is sent until you press Send.'}
      </p>

      <button type="button" className="tray-evaluations" onClick={onOpenEvaluations}>
        <span>
          <Icon name="checklist" size={15} />
          Open a saved evaluation
        </span>
        <span className="tray-count">
          {evaluationCount} recorded
          <Icon name="forward" size={13} />
        </span>
      </button>
    </div>
  )
}
