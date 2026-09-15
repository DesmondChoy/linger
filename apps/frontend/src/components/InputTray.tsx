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
  const [previewed, setPreviewed] = useState<string | null>(null)
  const book = DEMO_BOOKS.find((item) => item.workId === workId) ?? DEMO_BOOKS[0]

  return (
    <div className="input-tray">
      <div className="tray-head">
        <p className="eyebrow">Try a line</p>
        <label className="tray-book">
          <span className="visually-hidden">Book</span>
          <select value={workId} onChange={(event) => setWorkId(event.target.value)} disabled={disabled}>
            {DEMO_BOOKS.map((item) => (
              <option key={item.workId} value={item.workId}>{item.title}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="tray-chips">
        {book.prompts.map((prompt) => (
          <button
            key={prompt.label}
            type="button"
            className="tray-chip"
            disabled={disabled}
            title={prompt.text}
            onMouseEnter={() => setPreviewed(prompt.label)}
            onMouseLeave={() => setPreviewed(null)}
            onFocus={() => setPreviewed(prompt.label)}
            onBlur={() => setPreviewed(null)}
            onClick={() => onFill(prompt.text)}
          >
            {prompt.label}
          </button>
        ))}
      </div>

      <p className="tray-watch" aria-live="polite">
        {book.prompts.find((prompt) => prompt.label === previewed)?.watch
          ?? 'Pick one to fill the box. You can edit it, and nothing is sent until you press Send.'}
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
