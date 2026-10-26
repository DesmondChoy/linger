import type { ScenarioIndex, ScenarioSummary } from './types'

type Props = {
  snapshot: ScenarioIndex
  onOpen: (scenario: ScenarioSummary) => void
  onClose: () => void
  closeLabel: string
}

/** Synthetic scenarios grouped by the objective catalog's menu families. */
export function ScenarioGallery({ snapshot, onOpen, onClose, closeLabel }: Props) {
  const families = snapshot.families
    .map((family) => ({ ...family, scenarios: snapshot.scenarios.filter((scenario) => scenario.family === family.id) }))
    .filter((family) => family.scenarios.length > 0)

  return (
    <main className="scenario-gallery">
      <header className="scenario-gallery-head">
        <div>
          <p className="eyebrow">Synthetic scenarios</p>
          <h1>Replay a recorded evaluation</h1>
          <p className="muted">
            Each scenario pairs an invented reader with the memories placed in their account and a person-written answer key. Opening one replays exactly what a
            build of Linger recorded: read-only, with no model calls.
          </p>
        </div>
        <button type="button" className="quiet-button" onClick={onClose}>{closeLabel}</button>
      </header>

      {families.map((family) => (
        <section key={family.id} className="scenario-family" aria-labelledby={`family-${family.id}`}>
          <h2 id={`family-${family.id}`}>{family.label}</h2>
          <ul className="scenario-cards">
            {family.scenarios.map((scenario) => {
              const run = scenario.runs[0]
              return (
                <li key={scenario.id}>
                  <button type="button" className="scenario-card" onClick={() => onOpen(scenario)}>
                    <strong>{scenario.title}</strong>
                    <span className="scenario-dated">{scenario.dated}</span>
                    <span className="scenario-description">{scenario.description}</span>
                    <span className="scenario-tally">
                      <b className={run.failed ? 'has-failures' : 'all-passed'}>{run.passed}/{run.total} scenes passed</b>
                      {run.executionFailures > 0 && <small>{run.executionFailures} execution {run.executionFailures === 1 ? 'fault' : 'faults'}</small>}
                      {scenario.runs.length > 1 && <small>{scenario.runs.length} recorded runs</small>}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </main>
  )
}
