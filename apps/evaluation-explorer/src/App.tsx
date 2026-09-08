import { useEffect, useRef, useState } from 'react'
import catalog from './catalog.json'
import { Graph } from './Graph'
import { Icon } from './Icon'
import { Inspector } from './Inspector'
import { objectiveScenes } from './scenarios'
import type { InspectorSelection } from './types'

function defaultRoutes() {
  const routes = objectiveScenes.find(value => value.objectiveId === 'grounded_book_reflection')
  if (!routes) throw new Error('The grounded book reflection route is missing.')
  return routes
}

const initialRoutes = defaultRoutes()

export default function App() {
  const [routes, setRoutes] = useState(initialRoutes)
  const [sceneId, setSceneId] = useState(initialRoutes.scenes[0].id)
  const [selection, setSelection] = useState<InspectorSelection | null>(null)
  const [stepIndex, setStepIndex] = useState<number | null>(null)
  const explainButton = useRef<HTMLButtonElement>(null)
  const scene = routes.scenes.find(value => value.id === sceneId) ?? routes.scenes[0]
  const objective = catalog.objectives.find(value => value.id === routes.objectiveId)
  const step = stepIndex === null ? null : scene.steps[stepIndex] ?? null

  const endWalkthrough = () => {
    setStepIndex(null)
    requestAnimationFrame(() => explainButton.current?.focus())
  }

  useEffect(() => {
    if (stepIndex === null || selection) return
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLSelectElement || event.target instanceof HTMLInputElement) return
      if (event.key === 'ArrowRight') { event.preventDefault(); setStepIndex(index => Math.min(scene.steps.length - 1, (index ?? 0) + 1)) }
      if (event.key === 'ArrowLeft') { event.preventDefault(); setStepIndex(index => Math.max(0, (index ?? 0) - 1)) }
      if (event.key === 'Escape') { event.preventDefault(); setStepIndex(null); requestAnimationFrame(() => explainButton.current?.focus()) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stepIndex, scene.steps.length, selection])

  if (!objective) return <main className="load-error"><h1>Objective unavailable</h1><p>Refresh the repository catalog snapshot and restart the explorer.</p></main>

  const selectObjective = (id: string) => {
    const next = objectiveScenes.find(value => value.objectiveId === id)
    if (!next) return
    setRoutes(next)
    setSceneId(next.scenes[0].id)
    setStepIndex(null)
    setSelection(null)
  }

  const inspect = (value: InspectorSelection) => { setStepIndex(null); setSelection(value) }

  return <div className={`explorer status-${scene.status} ${step ? 'is-explaining' : ''}`}>
    <header className="app-header">
      <a className="wordmark" href="./" aria-label="Linger evaluation explorer home"><span className="brand-mark"><span /><span /></span>Linger<span className="wordmark-detail">Evaluation explorer</span></a>
      <div className="selection-control">
        <div className="objective-select-wrap"><label className="visually-hidden" htmlFor="objective-select">Evaluation objective</label><select id="objective-select" value={routes.objectiveId} onChange={event => selectObjective(event.target.value)}>{catalog.families.map(family => <optgroup key={family.id} label={family.label}>{catalog.objectives.filter(item => item.family === family.id).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</optgroup>)}</select><Icon name="chevron" size={19} /></div>
        <div className="scene-select-wrap"><label htmlFor="scene-select">Scene</label><select id="scene-select" value={scene.id} onChange={event => { setSceneId(event.target.value); setStepIndex(null) }}>{routes.scenes.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><Icon name="chevron" size={15} /></div>
      </div>
      <nav className="header-actions" aria-label="Explorer"><button className="text-button history-button" onClick={() => inspect({ kind: 'history' })}><Icon name="history" size={19} /><span>History</span></button><button className="icon-button" aria-label="About the explorer" onClick={() => inspect({ kind: 'about' })}><Icon name="info" size={23} /></button></nav>
    </header>

    <main className="workspace" id="main-content">
      <div className="context-bar"><button className={`scope-badge ${scene.status === 'target' ? 'is-target' : ''}`} onClick={() => inspect({ kind: 'scene' })}><span className="scope-dot" />{scene.status === 'target' ? 'Target architecture' : scene.status === 'component' ? 'Component preview' : 'Architecture preview'}<Icon name="info" size={14} /></button><span className="context-hint"><span className="desktop-hint">{step ? 'Guided explanation' : 'Explore the expected route'}</span><span className="mobile-hint">{step ? 'Following each step' : 'Swipe to explore the map'}</span></span></div>
      <div className="scene-caption" aria-live="polite"><p>{scene.summary}</p></div>
      <div className="map-stage"><Graph key={`${routes.objectiveId}:${scene.id}`} scene={scene} step={step} onSelect={inspect} /></div>

      <div className="exploration-controls">
        <div className="detail-actions"><button className="text-button" onClick={() => inspect({ kind: 'scene' })}><Icon name="input" size={19} />Scene inputs</button><button className="text-button" onClick={() => inspect({ kind: 'criteria' })}><Icon name="checklist" size={19} />What this tests</button></div>
        <button ref={explainButton} className="primary-button" onClick={() => setStepIndex(0)} aria-expanded={stepIndex !== null}><Icon name="play" size={19} />Explain step by step</button>
      </div>

      {step && stepIndex !== null && <section className="walkthrough" aria-label="Guided explanation">
        <div className="walkthrough-top"><span>Step {stepIndex + 1} of {scene.steps.length}</span><button className="icon-button" onClick={endWalkthrough} aria-label="Exit explanation"><Icon name="close" size={20} /></button></div>
        <div className="walkthrough-copy" aria-live="polite" aria-atomic="true"><h2>{step.title}</h2><p>{step.description}</p></div>
        <div className="walkthrough-bottom"><div className="step-dots" aria-hidden="true">{scene.steps.map((item, index) => <span key={item.title} className={index === stepIndex ? 'current' : index < stepIndex ? 'previous' : ''} />)}</div><div className="step-actions"><button className="icon-button" aria-label="Previous step" disabled={stepIndex === 0} onClick={() => setStepIndex(Math.max(0, stepIndex - 1))}><Icon name="back" size={20} /></button>{stepIndex === scene.steps.length - 1 ? <button className="next-button" onClick={endWalkthrough}>Finish<Icon name="close" size={17} /></button> : <button className="next-button" onClick={() => setStepIndex(stepIndex + 1)}>Next<Icon name="forward" size={17} /></button>}</div></div>
      </section>}
    </main>

    <footer className="app-footer"><button onClick={() => inspect({ kind: 'about' })}><span className="handoff-mark" />Application-controlled handoffs</button><span>{catalog.objectives.length} objectives, distinct ways to collaborate</span></footer>
    <Inspector selection={selection} scene={scene} objective={objective} onClose={() => setSelection(null)} />
  </div>
}
