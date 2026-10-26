import { useEffect, useState } from 'react'
import { ScenarioGallery } from './ScenarioGallery'
import { ScenarioReplay } from './ScenarioReplay'
import type { Scenario, ScenarioIndex, ScenarioSummary } from './types'

type Props = {
  onHome: () => void
  closeLabel?: string
  signedIn: boolean
  onOpenLive: () => void
}

// One lazily loaded module per scenario, so opening one downloads only that run.
const scenarioFiles = import.meta.glob<Scenario>(['./scenarios/*.json', '!./scenarios/index.json'], { import: 'default' })

function loadScenario(id: string): Promise<Scenario> {
  const load = scenarioFiles[`./scenarios/${id}.json`]
  return load ? load() : Promise.reject(new Error(`No recorded scenario ${id}`))
}

/** The synthetic-scenario surface: a gallery, then one scenario's recorded run. */
export function Scenarios({ onHome, closeLabel = 'Back to start', signedIn, onOpenLive }: Props) {
  const [index, setIndex] = useState<ScenarioIndex | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scenario, setScenario] = useState<Scenario | null>(null)

  useEffect(() => {
    import('./scenarios/index.json')
      .then((module) => setIndex(module.default as ScenarioIndex))
      .catch(() => setError('The recorded scenarios could not be loaded.'))
  }, [])

  function open(summary: ScenarioSummary) {
    setError(null)
    loadScenario(summary.id)
      .then(setScenario)
      .catch(() => setError(`${summary.title} could not be loaded.`))
  }

  if (error) return <main className="scenario-gallery"><p className="error">{error}</p></main>
  if (!index) return <main className="scenario-gallery"><p className="muted">Loading recorded scenarios…</p></main>
  if (scenario) return <ScenarioReplay scenario={scenario} onBack={() => setScenario(null)} onHome={onHome} signedIn={signedIn} onOpenLive={onOpenLive} />
  return <ScenarioGallery snapshot={index} onOpen={open} onClose={onHome} closeLabel={closeLabel} />
}
