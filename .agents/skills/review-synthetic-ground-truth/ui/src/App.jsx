import { useEffect, useMemo, useState } from 'react'
import { decisionPayload, reviewProgress, toggleId } from './review.js'

function tokenFromLocation() {
  return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
}

const reviewToken = tokenFromLocation()

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Review-Token': reviewToken,
      ...options.headers,
    },
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || 'The review could not complete this request.')
  return body
}

function Hash({ value }) {
  return <code title={value}>{value.slice(0, 12)}</code>
}

function StatusPill({ children, tone = 'neutral' }) {
  return <span className={`status-pill is-${tone}`}>{children}</span>
}

function InputRecord({ item }) {
  return (
    <article className="input-record">
      <header>
        <span className="record-kind">{item.kind}</span>
        <code>{item.id}</code>
        {item.role ? <StatusPill tone={item.role === 'expected source' || item.role === 'relevant' ? 'positive' : 'neutral'}>{item.role}</StatusPill> : null}
      </header>
      {item.text ? <blockquote>{item.text}</blockquote> : <p className="empty-copy">No free-text input.</p>}
      {item.propIds?.length ? <p className="record-links">Props: {item.propIds.join(', ')}</p> : null}
    </article>
  )
}

function OutcomeList({ title, items, tone }) {
  return (
    <section className={`outcome-list is-${tone}`}>
      <h4>{title}</h4>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  )
}

function CurationExpectation({ value }) {
  if (!value) return null
  const expected = value.expected
  const action = expected?.action
  return (
    <section className="typed-expectation">
      <div className="field-pair">
        <span>Primary behavior</span>
        <strong>{value.primary_behavior.replaceAll('_', ' ')}</strong>
      </div>
      <div className="field-pair">
        <span>Expected response</span>
        <strong>{action?.action?.replaceAll('_', ' ') ?? expected.kind.replaceAll('_', ' ')}</strong>
      </div>
      {action?.source_memory_ids?.length ? (
        <div className="source-id-list">
          <span>Expected sources</span>
          {action.source_memory_ids.map((id) => <code key={id}>{id}</code>)}
        </div>
      ) : null}
      {action?.max_summary_words ? <p className="constraint">Maximum summary length: {action.max_summary_words} words</p> : null}
      {action?.semantic_review ? (
        <div className="semantic-review">
          <h4>Semantic review criteria</h4>
          <ul>{action.semantic_review.criteria.map((item) => <li key={item}>{item}</li>)}</ul>
          {action.semantic_review.forbidden_claims.length ? (
            <>
              <h4>Forbidden semantic claims</h4>
              <ul>{action.semantic_review.forbidden_claims.map((item) => <li key={item}>{item}</li>)}</ul>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function GroundTruthDetails({ row }) {
  return (
    <div className="ground-truth-details">
      {row.capture ? (
        <section className="typed-expectation">
          <div className="field-pair">
            <span>Capture expectation</span>
            <strong>{row.capture.kind.replaceAll('_', ' ')}</strong>
          </div>
          {row.capture.span ? <blockquote className="exact-quote">{row.capture.span.text}</blockquote> : null}
        </section>
      ) : null}
      <CurationExpectation value={row.curation} />
      {row.propRelevance.length ? (
        <section className="relevance-grid">
          <h4>Prop relevance</h4>
          {row.propRelevance.map((item) => (
            <div key={item.prop_id}>
              <code>{item.prop_id}</code>
              <StatusPill tone={item.relevance === 'relevant' ? 'positive' : 'neutral'}>{item.relevance}</StatusPill>
            </div>
          ))}
        </section>
      ) : null}
      {row.spans.length ? (
        <section className="span-list">
          <h4>Exact source spans</h4>
          {row.spans.map((span) => (
            <div className="span-record" key={`${span.source_id}-${span.start_codepoint}-${span.end_codepoint}`}>
              <div><code>{span.source_id}</code><span>{span.start_codepoint}–{span.end_codepoint}</span></div>
              <blockquote>{span.text}</blockquote>
            </div>
          ))}
        </section>
      ) : null}
      <div className="outcome-columns">
        <OutcomeList title="Expected outcomes" items={row.expectedOutcomes} tone="expected" />
        <OutcomeList title="Prohibited outcomes" items={row.prohibitedOutcomes} tone="prohibited" />
      </div>
      {(row.pairing || row.evidence.length) ? (
        <details className="technical-details">
          <summary>Validation evidence and pairing</summary>
          {row.pairing ? <pre>{JSON.stringify(row.pairing, null, 2)}</pre> : null}
          {row.evidence.length ? <pre>{JSON.stringify(row.evidence, null, 2)}</pre> : null}
        </details>
      ) : null}
    </div>
  )
}

function ReviewRow({ row, reviewed, flagged, onReview, onFlag }) {
  return (
    <article className={`review-row ${reviewed ? 'is-reviewed' : ''} ${flagged ? 'is-flagged' : ''}`} id={row.proposalId}>
      <header className="row-heading">
        <div className="scene-index" aria-hidden="true">{String(row.sceneOrder).padStart(2, '0')}</div>
        <div className="row-title">
          <div className="row-kicker"><code>{row.sceneId}</code><span>·</span><code>{row.objectiveId}</code></div>
          <h2>{row.summary}</h2>
        </div>
        <div className="row-controls">
          <button className={`flag-button ${flagged ? 'is-active' : ''}`} onClick={onFlag} type="button">
            {flagged ? 'Changes requested' : 'Needs changes'}
          </button>
          <label className="review-check">
            <input checked={reviewed} onChange={onReview} type="checkbox" />
            <span className="check-mark" aria-hidden="true">{reviewed ? '✓' : ''}</span>
            <span>Approve this proposal</span>
          </label>
        </div>
      </header>
      <div className="review-columns">
        <section className="source-column">
          <div className="column-heading"><span>01</span><h3>Scene inputs</h3></div>
          <p className="column-note">Everything available to this Scene before runtime.</p>
          <div className="input-stack">{row.inputs.map((item) => <InputRecord item={item} key={item.id} />)}</div>
        </section>
        <section className="truth-column">
          <div className="column-heading"><span>02</span><h3>Proposed Ground truth</h3></div>
          <p className="column-note">The answer key that will become authoritative if approved.</p>
          <GroundTruthDetails row={row} />
        </section>
      </div>
    </article>
  )
}

function ProofStrip({ rows, reviewedIds, flaggedIds }) {
  return (
    <nav aria-label="Ground truth review progress" className="proof-strip">
      {rows.map((row) => {
        const reviewed = reviewedIds.has(row.proposalId)
        const flagged = flaggedIds.has(row.proposalId)
        return (
          <a className={reviewed ? 'is-reviewed' : flagged ? 'is-flagged' : ''} href={`#${row.proposalId}`} key={row.proposalId} title={`${row.sceneId}: ${row.summary}`}>
            <span>{row.sceneOrder}</span>
          </a>
        )
      })}
    </nav>
  )
}

function App() {
  const [review, setReview] = useState(null)
  const [reviewedIds, setReviewedIds] = useState(new Set())
  const [flaggedIds, setFlaggedIds] = useState(new Set())
  const [fatalError, setFatalError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [completed, setCompleted] = useState(null)

  useEffect(() => {
    api('/api/review').then(setReview).catch((error) => setFatalError(error.message))
  }, [])

  const progress = useMemo(
    () => reviewProgress(review?.rows ?? [], reviewedIds),
    [review, reviewedIds],
  )

  function toggleReviewed(proposalId) {
    setSubmitError('')
    setReviewedIds((current) => toggleId(current, proposalId))
    setFlaggedIds((current) => {
      const next = new Set(current)
      next.delete(proposalId)
      return next
    })
  }

  function toggleFlagged(proposalId) {
    setSubmitError('')
    setFlaggedIds((current) => toggleId(current, proposalId))
    setReviewedIds((current) => {
      const next = new Set(current)
      next.delete(proposalId)
      return next
    })
  }

  async function submit(action) {
    setSubmitting(true)
    setSubmitError('')
    try {
      await api('/api/decision', {
        method: 'POST',
        body: JSON.stringify(decisionPayload(action, reviewedIds, flaggedIds)),
      })
      setCompleted(action)
    } catch (error) {
      setSubmitError(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (fatalError) {
    return <main className="state-screen"><p className="eyebrow">Review unavailable</p><h1>The package could not be opened.</h1><p>{fatalError}</p></main>
  }
  if (!review) return <main className="state-screen"><p className="loading">Validating and arranging the Ground truth ledger…</p></main>
  if (completed) {
    const confirmed = completed === 'confirm'
    return (
      <main className="completed-screen">
        <div className={`completion-mark ${confirmed ? '' : 'is-revision'}`} aria-hidden="true">{confirmed ? '✓' : '↺'}</div>
        <p className="eyebrow">{confirmed ? 'Ground truth confirmed' : 'Changes requested'}</p>
        <h1>{confirmed ? 'The agent can now continue to the supported evaluation.' : 'The agent will return to discuss your corrections.'}</h1>
        <p>This local review server is closing. Return to Codex when this page becomes unavailable.</p>
      </main>
    )
  }

  const confirmDisabled = !progress.complete || flaggedIds.size > 0 || submitting
  return (
    <main className="review-shell">
      <header className="review-header">
        <div>
          <p className="eyebrow">Linger · independent Ground truth review</p>
          <h1>Read every source. Approve every answer key.</h1>
          <p className="intro">The generated JSON remains the proposal authority. Your confirmed review creates a separate, hash-bound adoption record.</p>
        </div>
        <div className="package-stamp">
          <span>Package proof</span>
          <dl>
            <div><dt>Backstory</dt><dd><Hash value={review.package.backstorySha256} /></dd></div>
            <div><dt>Ground truth</dt><dd><Hash value={review.package.proposedGroundTruthSha256} /></dd></div>
            <div><dt>Status</dt><dd>{review.package.groundTruthStatus}</dd></div>
          </dl>
        </div>
      </header>

      <section className="context-band">
        <div><span>Backstory</span><strong>{review.package.backstoryId}</strong><p>{review.package.backstoryContext}</p></div>
        <div><span>Objectives</span><strong>{review.package.objectiveIds.join(', ')}</strong><p>{review.replay.note}</p></div>
        {review.report.text ? (
          <details>
            <summary>Pre-generation report and generator prompt</summary>
            <pre>{review.report.text}</pre>
          </details>
        ) : null}
      </section>

      <div className="ledger-layout">
        <ProofStrip flaggedIds={flaggedIds} reviewedIds={reviewedIds} rows={review.rows} />
        <section className="row-stack">
          {review.rows.map((row) => (
            <ReviewRow
              flagged={flaggedIds.has(row.proposalId)}
              key={row.proposalId}
              onFlag={() => toggleFlagged(row.proposalId)}
              onReview={() => toggleReviewed(row.proposalId)}
              reviewed={reviewedIds.has(row.proposalId)}
              row={row}
            />
          ))}
        </section>
      </div>

      <footer className="action-rail">
        <div className="progress-copy">
          <strong>{progress.reviewed} of {progress.total} approved</strong>
          <span>{flaggedIds.size ? `${flaggedIds.size} marked for changes` : progress.complete ? 'Every row is ready.' : 'Confirm unlocks after every row is approved.'}</span>
          {submitError ? <span className="submit-error" role="alert">{submitError}</span> : null}
        </div>
        <div className="actions">
          <button className="changes-button" disabled={submitting} onClick={() => submit('make_changes')} type="button">Make Changes</button>
          <button className="confirm-button" disabled={confirmDisabled} onClick={() => submit('confirm')} type="button">
            {submitting ? 'Sending decision…' : review.replay.confirmLabel}
          </button>
        </div>
      </footer>
    </main>
  )
}

export default App
