import { useEffect, useState } from 'react'
import { PersonaGallery } from './PersonaGallery'
import { PersonaReplay } from './PersonaReplay'
import type { Persona, PersonaIndex, PersonaSummary } from './types'

type Props = {
  onHome: () => void
  closeLabel?: string
}

// One lazily loaded module per persona, so opening one downloads only that run.
const personaFiles = import.meta.glob<Persona>(['./personas/*.json', '!./personas/index.json'], { import: 'default' })

function loadPersona(id: string): Promise<Persona> {
  const load = personaFiles[`./personas/${id}.json`]
  return load ? load() : Promise.reject(new Error(`No recorded persona ${id}`))
}

/** The synthetic-persona surface: a gallery, then one persona's recorded run. */
export function Personas({ onHome, closeLabel = 'Back to start' }: Props) {
  const [index, setIndex] = useState<PersonaIndex | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [persona, setPersona] = useState<Persona | null>(null)

  useEffect(() => {
    import('./personas/index.json')
      .then((module) => setIndex(module.default as PersonaIndex))
      .catch(() => setError('The recorded personas could not be loaded.'))
  }, [])

  function open(summary: PersonaSummary) {
    setError(null)
    loadPersona(summary.id)
      .then(setPersona)
      .catch(() => setError(`${summary.title} could not be loaded.`))
  }

  if (error) return <main className="persona-gallery"><p className="error">{error}</p></main>
  if (!index) return <main className="persona-gallery"><p className="muted">Loading recorded personas…</p></main>
  if (persona) return <PersonaReplay persona={persona} onBack={() => setPersona(null)} onHome={onHome} />
  return <PersonaGallery snapshot={index} onOpen={open} onClose={onHome} closeLabel={closeLabel} />
}
