import { useMemo, useState } from 'react'
import { Graph, Inspector, playableScenarios } from '@linger/architecture-map'
import type { EvaluationRun, EvaluationScenario, InspectorSelection } from '@linger/architecture-map'
import { buildEvaluationView, failureProse } from './evaluationScene'

type Props = { onClose: () => void }

function scenarioTitle(scenario: EvaluationScenario): string {
  return scenario.id
    .replace(/--.*$/, '')
    .replaceAll('-', ' ')
    .replace(/^\w/, (character) => character.toUpperCase())
}

function tally(run: EvaluationRun): string {
  return run.total === null || run.passed === null ? '—' : `${run.passed}/${run.total}`
}

function tone(run: EvaluationRun): string {
  if (run.total === null || run.passed === null) return 'unknown'
  if (run.passed === run.total) return 'good'
  return run.passed === 0 ? 'bad' : 'partial'
}

export function SavedEvaluation({ onClose }: Props) {
  const [scenarioId, setScenarioId] = useState(playableScenarios[0]?.id ?? '')
  const scenario = playableScenarios.find((item) => item.id === scenarioId) ?? playableScenarios[0]

  const [runId, setRunId] = useState<string | null>(null)
  const [sceneIndex, setSceneIndex] = useState(0)
  const [selection, setSelection] = useState<InspectorSelection | null>(null)

  const run = scenario?.runs.find((item) => item.id === runId) ?? scenario?.runs[0]
  const runScene = run?.scenes[Math.min(sceneIndex, (run?.scenes.length ?? 1) - 1)]
  const scene = scenario?.scenes.find((item) => item.id === runScene?.sceneId)

  const view = useMemo(() => (
    run && runScene && scene ? buildEvaluationView({ run, runScene, scene }) : null
  ), [run, runScene, scene])

  if (!scenario || !run) {
    return (
      <section className="saved-evaluation" aria-label="Saved evaluation">
        <p className="empty">No recorded evaluation runs are available in this checkout.</p>
      </section>
    )
  }

  // Distinct builds, not repeated trials: the set is a record of change.
  const builds = new Set(scenario.runs.map((item) => item.systemVariant)).size
  const activeProps = scenario.props.filter((prop) => prop.activeScenes.includes(runScene?.sceneId ?? ''))

  return (
    <section className="saved-evaluation" aria-label="Saved evaluation">
      <header className="evaluation-head">
        <div>
          <p className="eyebrow">You are reading a saved evaluation</p>
          <p className="evaluation-lede">
            Not a live conversation. A made-up reader sent one fixed message, it was answered by one
            particular build of Linger, and afterwards a person compared the answer to what they had
            decided a good answer must do.
          </p>
        </div>
        <button type="button" className="quiet-button" onClick={onClose}>Back to chat</button>
      </header>

      <div className="evaluation-pickers">
        <label>
          <span className="visually-hidden">Scenario</span>
          <select
            value={scenario.id}
            onChange={(event) => { setScenarioId(event.target.value); setRunId(null); setSceneIndex(0) }}
          >
            {playableScenarios.map((item) => (
              <option key={item.id} value={item.id}>{scenarioTitle(item)}</option>
            ))}
          </select>
        </label>
        {run.scenes.length > 1 && (
          <label>
            <span className="visually-hidden">Scene</span>
            <select value={sceneIndex} onChange={(event) => setSceneIndex(Number(event.target.value))}>
              {run.scenes.map((item, index) => (
                <option key={item.sceneId ?? index} value={index}>{item.sceneId}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      <section className="persona-card">
        <div className="persona-head">
          <b>{scenario.persona.id?.replace(/^person-/, '').replace(/^\w/, (c) => c.toUpperCase()) ?? 'Reader'}</b>
          <span className="subtle">invented persona</span>
        </div>
        <p>{scenario.persona.context}</p>
        {activeProps.length > 0 && (
          <div className="seeded-props">
            <p className="eyebrow">Placed in the account before the run</p>
            {activeProps.map((prop) => <blockquote key={prop.id}>{prop.sourceText}</blockquote>)}
          </div>
        )}
        {scene && (
          <p className="persona-note">
            How far they have read is not given &mdash; it has to be worked out from what is placed here
            and what they say, and working it out is part of what this scene tests.
          </p>
        )}
      </section>

      <section className="run-strip">
        <div className="run-strip-head">
          <b>The same scene was answered by {scenario.runs.length} recorded runs</b>
          <span className="subtle">
            {builds} distinct build{builds === 1 ? '' : 's'} &middot; grouped by score, not a timeline
          </span>
        </div>
        <div className="run-chips">
          {[...scenario.runs]
            .sort((a, b) => (b.passed ?? -1) - (a.passed ?? -1))
            .map((item) => (
              <button
                key={item.id}
                type="button"
                className={`run-chip ${tone(item)} ${item.id === run.id ? 'is-selected' : ''}`}
                onClick={() => { setRunId(item.id); setSceneIndex(0) }}
              >
                <b>{tally(item)}</b>
                <span>{item.label}</span>
              </button>
            ))}
        </div>
        <p className="muted">
          Each run is named for the change it was testing, so this is a record of the system being
          worked on &mdash; not one build being unreliable.
        </p>
      </section>

      {view && scene ? (
        <>
          <div className="scene-line">
            <p className="eyebrow">The fixed message</p>
            <p>{scene.line}</p>
            <small>Editing it would unbind the answer key, so it cannot be changed.</small>
          </div>

          <p className="evaluation-verdict">
            {view.retrievalMissing
              ? 'The adopted key required a look-up. This build never made one.'
              : 'The route this build actually took.'}
          </p>

          <div className="map-stage">
            <Graph
              key={view.scene.id}
              scene={view.scene}
              step={null}
              onSelect={setSelection}
              description="recorded route for this run"
            />
          </div>

          <section className="evaluation-checks">
            <div className="checks-head">
              <p className="eyebrow">What the key asked</p>
              <span className="subtle">written and approved by a person</span>
            </div>
            <ul className="key-outcomes">
              {view.expected.map((text) => <li key={text}><b>must</b><span>{text}</span></li>)}
              {view.prohibited.map((text) => <li key={text}><b className="prohibited">must not</b><span>{text}</span></li>)}
            </ul>

            {view.objectives.length > 0 && (
              <ul className="objective-results">
                {view.objectives.map((objective, index) => (
                  <li key={`${objective.objectiveId}-${index}`} className={objective.passed ? 'passed' : 'failed'}>
                    <span className="trace-status">{objective.passed ? 'passed' : 'missed'}</span>
                    <b>{objective.objectiveId?.replaceAll('_', ' ')}</b>
                    {objective.failures.length > 0 && (
                      <ul>
                        {objective.failures.map((code) => <li key={code}>{failureProse(code)}</li>)}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <details className="raw-detail">
            <summary>What this build replied</summary>
            <p className="response-text">{runScene?.reply || 'No reply was recorded.'}</p>
          </details>

          <p className="evaluation-caution">
            <b>How to read a miss:</b> it means this build did not do what the key asked. The key is a
            human judgement, so a miss can also mean the key itself needs revisiting &mdash; which is why
            later builds were changed and re-run rather than the result being filed as a verdict.
            {run.model && <> Run on <code>{run.model}</code>, build <code>{run.systemVariant}</code>.</>}
          </p>
        </>
      ) : (
        <p className="empty">This run records no detail for the selected scene.</p>
      )}

      {view && (
        <Inspector selection={selection} scene={view.scene} onClose={() => setSelection(null)} />
      )}
    </section>
  )
}
