import { useState } from 'react'
import { Icon } from '@linger/architecture-map'
import { ANY_BOOK, DEMO_BOOKS, DEMO_PATHS, variantsFor, type DemoPath } from './demoPrompts'

type Props = {
  disabled: boolean
  /** Fills the composer with editable text. Never sends. */
  onFill: (text: string) => void
  /** Starts a fresh session below the current one, for a path's "new chat" step. */
  onNewChat: () => void
  /** False while the current chat is still empty, so a new chat would change nothing. */
  canStartNewChat: boolean
  /** Opens the recorded synthetic-persona replays. */
  onOpenPersonas: () => void
}

type Active = { path: DemoPath; variant: number; done: Set<number> }

function pickVariant(options: number[], avoid?: number): number {
  const choices = options.length > 1 ? options.filter((index) => index !== avoid) : options
  return choices[Math.floor(Math.random() * choices.length)]
}

/**
 * Two ways in, kept visually distinct because they make different claims.
 *
 * A guided path is a live conversation you could have typed: nothing checks it,
 * and following it is optional. A persona replay is a recorded run with an
 * answer key a person adopted. Collapsing them would imply the first has
 * ground truth behind it.
 */
export function InputTray({ disabled, onFill, onNewChat, canStartNewChat, onOpenPersonas }: Props) {
  const [active, setActive] = useState<Active | null>(null)
  const [previewed, setPreviewed] = useState<number | null>(null)
  const [workId, setWorkId] = useState(ANY_BOOK)
  const options = active ? variantsFor(active.path, workId) : []
  const start = (path: DemoPath, book: string) => {
    const choices = variantsFor(path, book)
    setActive(choices.length ? { path, variant: pickVariant(choices), done: new Set() } : null)
  }

  const variant = active ? active.path.variants[active.variant] : null
  const next = variant ? variant.steps.findIndex((_, index) => !active!.done.has(index)) : -1
  const focused = previewed ?? (next >= 0 ? next : null)
  const markDone = (index: number) => setActive((current) => current && {
    ...current, done: new Set(current.done).add(index),
  })

  return (
    <div className="input-tray">
      <div className="tray-head">
        <p className="eyebrow">Try a conversation</p>
        <div className="tray-head-actions">
          <label className="tray-book">
            <span className="visually-hidden">Book</span>
            <select
              value={workId}
              disabled={disabled}
              onChange={(event) => {
                setWorkId(event.target.value)
                if (active) start(active.path, event.target.value)
              }}
            >
              <option value={ANY_BOOK}>Any book</option>
              {DEMO_BOOKS.map((book) => <option key={book.workId} value={book.workId}>{book.title}</option>)}
            </select>
          </label>
          {active && (
            <button type="button" className="tray-link" onClick={() => setActive(null)}>
              All paths
            </button>
          )}
        </div>
      </div>

      {!active || !variant ? (
        <>
          <div className="tray-chips">
            {DEMO_PATHS.map((path) => (
              <button
                key={path.id}
                type="button"
                className="tray-chip"
                disabled={disabled || variantsFor(path, workId).length === 0}
                title={path.shows}
                onClick={() => start(path, workId)}
              >
                {path.label}
              </button>
            ))}
          </div>
          <p className="tray-watch">
            Each path is a short conversation that shows one behaviour. Follow it, skip around, or type your own; nothing is sent until you press Send.
          </p>
        </>
      ) : (
        <div className="tray-path">
          <div className="tray-path-head">
            <div>
              <strong>{active.path.label}</strong>
              <span className="tray-path-meta">
                {variant.book ?? 'No book'}
                {options.length > 1 && ` · wording ${options.indexOf(active.variant) + 1} of ${options.length}`}
              </span>
            </div>
            {options.length > 1 && (
              <button
                type="button"
                className="tray-link"
                disabled={disabled}
                onClick={() => setActive({ ...active, variant: pickVariant(options, active.variant), done: new Set() })}
              >
                Try another wording
              </button>
            )}
          </div>
          {active.path.caveat && <p className="tray-caveat">{active.path.caveat}</p>}

          <ol className="tray-steps">
            {variant.steps.map((step, index) => {
              const state = active.done.has(index) ? 'is-done' : index === next ? 'is-next' : ''
              const hover = {
                onMouseEnter: () => setPreviewed(index),
                onMouseLeave: () => setPreviewed(null),
                onFocus: () => setPreviewed(index),
                onBlur: () => setPreviewed(null),
              }
              return (
                <li key={index} className={state}>
                  {step.kind === 'line' ? (
                    <button
                      type="button"
                      disabled={disabled}
                      title={step.text}
                      {...hover}
                      onClick={() => { onFill(step.text); markDone(index) }}
                    >
                      <span className="tray-step-mark" aria-hidden="true">{active.done.has(index) ? '✓' : index + 1}</span>
                      <span className="tray-step-label">{step.label}</span>
                      <span className="tray-step-text">{step.text}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="tray-step-new-chat"
                      disabled={disabled || !canStartNewChat}
                      {...hover}
                      onClick={() => { onNewChat(); markDone(index) }}
                    >
                      <span className="tray-step-mark" aria-hidden="true">{active.done.has(index) ? '✓' : index + 1}</span>
                      <span className="tray-step-label">Start a new chat</span>
                    </button>
                  )}
                </li>
              )
            })}
          </ol>

          <p className="tray-watch" aria-live="polite">
            {focused !== null ? <><b>Watch for:</b> {variant.steps[focused].watch}</> : 'Path complete. Pick another, or keep talking.'}
          </p>
        </div>
      )}

      <button type="button" className="tray-evaluations" onClick={onOpenPersonas}>
        <span>
          <Icon name="checklist" size={15} />
          Replay a synthetic persona
        </span>
        <span className="tray-count">
          recorded runs with answer keys
          <Icon name="forward" size={13} />
        </span>
      </button>
    </div>
  )
}
