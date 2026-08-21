import { useEffect, useMemo, useState } from 'react'
import { selectionError, suggestedObjectiveIds } from './selection.js'

function tokenFromLocation() {
  return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
}

const selectorToken = tokenFromLocation()

const objectiveIconPaths = {
  grounded_book_reflection: [
    'M3 4.5h5.5A3.5 3.5 0 0 1 12 8v12a3.5 3.5 0 0 0-3.5-3.5H3z',
    'M21 4.5h-5.5A3.5 3.5 0 0 0 12 8v12a3.5 3.5 0 0 1 3.5-3.5H21z',
  ],
  reviewed_automatic_memory_capture: [
    'M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4z',
    'm9 9 2 2 4-4',
  ],
  session_scoped_conversation_continuity: [
    'M4 5h16v11H8l-4 3z',
    'M8 9h8M8 12h6',
  ],
  longitudinal_memory_retrieval_with_isolation: [
    'M11 19a8 8 0 1 1 5.65-2.35L22 22',
    'M11 7v4l2.5 2.5',
  ],
  bounded_memory_curation: [
    'M6 5.5a2 2 0 1 0 0 .01',
    'M18 5.5a2 2 0 1 0 0 .01',
    'M12 18.5a2 2 0 1 0 0 .01',
    'M7.7 6.5 10.3 16M16.3 6.5 13.7 16M8 5.5h8',
  ],
  cross_source_tentative_connection: [
    'M9.5 14.5 14.5 9.5',
    'M7.5 17.5H6a4 4 0 0 1 0-8h3',
    'M16.5 6.5H18a4 4 0 0 1 0 8h-3',
  ],
  weak_evidence_safe_decline: [
    'M12 3 2.5 20h19z',
    'M12 9v4.5M12 17h.01',
  ],
  spoiler_boundary_clarification: [
    'M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 3z',
    'M17 9h3v11h-3M8 8h5M8 12h4',
  ],
  untrusted_content_injection_resistance: [
    'M12 3 20 6v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6z',
    'm8 8 8 8',
  ],
  sensitive_inference_and_capture_veto: [
    'M20.8 5.8a5.4 5.4 0 0 0-7.6 0L12 7l-1.2-1.2a5.4 5.4 0 0 0-7.6 7.6L12 22l8.8-8.6a5.4 5.4 0 0 0 0-7.6z',
    'M8 8l8 8',
  ],
}

function ObjectiveIcon({ objectiveId }) {
  return (
    <span className="objective-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        {objectiveIconPaths[objectiveId].map((path) => <path d={path} key={path} />)}
      </svg>
    </span>
  )
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Selector-Token': selectorToken,
      ...options.headers,
    },
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || 'The selector could not complete this request.')
  return body
}

function SelectionCount({ count }) {
  return (
    <div className="selection-count" role="status">
      <p className="count-value"><strong>{count}</strong> selected</p>
      <p className="count-note">Fewer objectives make a more coherent set.</p>
    </div>
  )
}

function ObjectiveCard({ objective, isSelected, badge, titlesById, onToggle, detailsPlacement }) {
  const detailsId = `${objective.id}-details`
  const partners = objective.combinesWellWith
    .map((partnerId) => titlesById[partnerId])
    .filter(Boolean)

  const className = [
    'objective-card',
    isSelected ? 'is-selected' : '',
    badge ? `has-badge is-${badge.tone}` : '',
  ].filter(Boolean).join(' ')

  return (
    <label className={className}>
      <input
        aria-describedby={detailsId}
        checked={isSelected}
        onChange={() => onToggle(objective.id)}
        type="checkbox"
      />
      <span className="checkbox" aria-hidden="true">{isSelected ? '✓' : ''}</span>
      <ObjectiveIcon objectiveId={objective.id} />
      <span className="objective-copy">
        <strong>{objective.title}</strong>
        {badge ? <span className="card-badge">{badge.label}</span> : null}
      </span>

      <span
        className={`objective-details is-${detailsPlacement}`}
        id={detailsId}
        role="tooltip"
      >
        <span className="details-hint">{objective.selectionHint}</span>
        <span className="details-summary">{objective.summary}</span>
        {badge ? <span className="details-note">{badge.detail}</span> : null}
        {partners.length > 0 ? (
          <span className="details-partners">
            <span className="details-label">Combines well with</span>
            <span className="partner-chips">
              {partners.map((title) => <span className="partner-chip" key={title}>{title}</span>)}
            </span>
          </span>
        ) : null}
      </span>
    </label>
  )
}

function App() {
  const [catalog, setCatalog] = useState(null)
  const [selected, setSelected] = useState([])
  const [fatalError, setFatalError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  useEffect(() => {
    api('/api/catalog').then(setCatalog).catch((error) => setFatalError(error.message))
  }, [])

  const validationError = useMemo(
    () => catalog ? selectionError(selected, catalog.constraints) : null,
    [catalog, selected],
  )
  const suggested = useMemo(
    () => catalog ? suggestedObjectiveIds(selected, catalog.objectives) : new Set(),
    [catalog, selected],
  )
  const titlesById = useMemo(
    () => Object.fromEntries((catalog?.objectives ?? []).map((objective) => [objective.id, objective.title])),
    [catalog],
  )
  const messageIsError = Boolean(submitError || (selected.length > 0 && validationError))

  function toggle(objectiveId) {
    setSubmitError('')
    setSelected((current) => current.includes(objectiveId)
      ? current.filter((id) => id !== objectiveId)
      : [...current, objectiveId])
  }

  function badgeFor(objective) {
    const constraint = (catalog.constraints ?? []).find(
      (entry) => entry.objectiveId === objective.id && entry.requiresAnyOtherObjective,
    )
    if (constraint) {
      return { tone: 'required', label: 'Needs a partner', detail: constraint.reason }
    }
    if (suggested.has(objective.id)) {
      return {
        tone: 'suggested',
        label: 'Pairs with your selection',
        detail: 'The catalog marks this objective as a good companion for what you already selected.',
      }
    }
    return null
  }

  async function confirmSelection() {
    setSubmitting(true)
    setSubmitError('')
    try {
      await api('/api/confirm', {
        method: 'POST',
        body: JSON.stringify({ objectiveIds: selected }),
      })
      setConfirmed(true)
    } catch (error) {
      setSubmitError(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (fatalError) {
    return (
      <main className="state-screen">
        <p className="eyebrow">Selector unavailable</p>
        <h1>The objective catalog could not be opened.</h1>
        <p>{fatalError}</p>
      </main>
    )
  }

  if (!catalog) {
    return <main className="state-screen"><p className="loading">Opening the objective catalog…</p></main>
  }

  if (confirmed) {
    return (
      <main className="confirmed-screen">
        <div className="confirmed-mark" aria-hidden="true">✓</div>
        <p className="eyebrow">Selection confirmed</p>
        <h1>{selected.length} evaluation {selected.length === 1 ? 'objective' : 'objectives'} ready.</h1>
        <p>Return to your agent. It now has the validated selection.</p>
      </main>
    )
  }

  return (
    <main className="selector-shell">
      <header className="selector-header">
        <div>
          <p className="eyebrow">Linger · synthetic journal evaluation</p>
          <h1>Choose what the evaluation should prove.</h1>
          <p className="intro">
            Select the fewest objectives that cover the behavior you want to examine.
            Hover an objective for details.
          </p>
        </div>
        <SelectionCount count={selected.length} />
      </header>

      <div className="objective-board">
        {catalog.families.map((family, familyIndex) => {
          const objectives = catalog.objectives.filter((objective) => objective.family === family.id)
          if (objectives.length === 0) return null
          // Only the first family has room to open downward.
          const detailsPlacement = familyIndex === 0 ? 'below' : 'above'
          return (
            <section aria-labelledby={`${family.id}-label`} className="objective-family" key={family.id}>
              <h2 className="family-heading" id={`${family.id}-label`}>
                <span className="family-label">{family.label}</span>
                <span className="family-summary">{family.summary}</span>
              </h2>
              <div className="family-grid">
                {objectives.map((objective) => (
                  <ObjectiveCard
                    badge={badgeFor(objective)}
                    detailsPlacement={detailsPlacement}
                    isSelected={selected.includes(objective.id)}
                    key={objective.id}
                    objective={objective}
                    onToggle={toggle}
                    titlesById={titlesById}
                  />
                ))}
              </div>
            </section>
          )
        })}
      </div>

      <footer className="action-rail">
        <div className={messageIsError ? 'selection-message is-error' : 'selection-message'} role="status">
          {submitError || (selected.length > 0 && validationError) || (selected.length === 0
            ? 'Select at least one objective to continue.'
            : 'Selection is valid and ready to confirm.')}
        </div>
        <div className="actions">
          <button className="clear-button" disabled={selected.length === 0 || submitting} onClick={() => setSelected([])} type="button">
            Clear
          </button>
          <button className="confirm-button" disabled={Boolean(validationError) || submitting} onClick={confirmSelection} type="button">
            {submitting ? 'Confirming…' : `Confirm ${selected.length || ''} ${selected.length === 1 ? 'objective' : 'objectives'}`}
          </button>
        </div>
      </footer>
    </main>
  )
}

export default App
