import type { PersonaIndex, PersonaSummary } from './types'

type Props = {
  snapshot: PersonaIndex
  onOpen: (persona: PersonaSummary) => void
  onClose: () => void
  closeLabel: string
}

/** Synthetic personas grouped by the objective catalog's menu families. */
export function PersonaGallery({ snapshot, onOpen, onClose, closeLabel }: Props) {
  const families = snapshot.families
    .map((family) => ({ ...family, personas: snapshot.personas.filter((persona) => persona.family === family.id) }))
    .filter((family) => family.personas.length > 0)

  return (
    <main className="persona-gallery">
      <header className="persona-gallery-head">
        <div>
          <p className="eyebrow">Synthetic personas</p>
          <h1>Replay a recorded evaluation</h1>
          <p className="muted">
            Invented readers, each with a person-written answer key. Opening one replays exactly what a
            build of Linger recorded: read-only, with no model calls.
          </p>
        </div>
        <button type="button" className="quiet-button" onClick={onClose}>{closeLabel}</button>
      </header>

      {families.map((family) => (
        <section key={family.id} className="persona-family" aria-labelledby={`family-${family.id}`}>
          <h2 id={`family-${family.id}`}>{family.label}</h2>
          <ul className="persona-cards">
            {family.personas.map((persona) => {
              const run = persona.runs[0]
              return (
                <li key={persona.id}>
                  <button type="button" className="persona-card" onClick={() => onOpen(persona)}>
                    <strong>{persona.title}</strong>
                    <span className="persona-dated">{persona.dated}</span>
                    <span className="persona-description">{persona.description}</span>
                    <span className="persona-tally">
                      <b className={run.failed ? 'has-failures' : 'all-passed'}>{run.passed}/{run.total} scenes passed</b>
                      {run.executionFailures > 0 && <small>{run.executionFailures} execution {run.executionFailures === 1 ? 'fault' : 'faults'}</small>}
                      {persona.runs.length > 1 && <small>{persona.runs.length} recorded runs</small>}
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
