import { useEffect, useRef, useState } from 'react'
import catalog from './catalog.json'
import { Graph } from './Graph'
import { Icon } from './Icon'
import { objectiveScenes } from './scenarios'
import type { InspectorSelection, ObjectiveScenes, Scene, WalkthroughStep } from './types'
import type { Objective } from './Inspector'

const DEFAULT_OBJECTIVE_ID = 'grounded_book_reflection'

function defaultRoutes(): ObjectiveScenes {
  const routes = objectiveScenes.find(value => value.objectiveId === DEFAULT_OBJECTIVE_ID)
  if (!routes) throw new Error('The grounded book reflection route is missing.')
  return routes
}

export interface ScenarioExplorerState {
  routes: ObjectiveScenes
  scene: Scene
  objective: Objective | undefined
  selection: InspectorSelection | null
  stepIndex: number | null
  step: WalkthroughStep | null
  /** Host applies this alongside its own base class so map CSS reacts to state. */
  stageClassName: string
  explainButton: React.RefObject<HTMLButtonElement | null>
  selectObjective: (id: string) => void
  selectScene: (id: string) => void
  inspect: (selection: InspectorSelection) => void
  closeInspector: () => void
  startWalkthrough: () => void
  endWalkthrough: () => void
  goToStep: (index: number) => void
}

/**
 * Selection and walkthrough state for the curated architecture explanations.
 *
 * The hook owns no layout, so the standalone explorer and the chat panel can
 * arrange the same pieces differently without duplicating this behaviour.
 */
export function useScenarioExplorer(): ScenarioExplorerState {
  const [routes, setRoutes] = useState(defaultRoutes)
  const [sceneId, setSceneId] = useState(() => defaultRoutes().scenes[0].id)
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

  return {
    routes, scene, objective, selection, stepIndex, step, explainButton,
    stageClassName: `status-${scene.status} ${step ? 'is-explaining' : ''}`,
    selectObjective: (id: string) => {
      const next = objectiveScenes.find(value => value.objectiveId === id)
      if (!next) return
      setRoutes(next)
      setSceneId(next.scenes[0].id)
      setStepIndex(null)
      setSelection(null)
    },
    selectScene: (id: string) => { setSceneId(id); setStepIndex(null) },
    inspect: (value: InspectorSelection) => { setStepIndex(null); setSelection(value) },
    closeInspector: () => setSelection(null),
    startWalkthrough: () => setStepIndex(0),
    endWalkthrough,
    goToStep: (index: number) => setStepIndex(index),
  }
}

/** Objective and Scene pickers, grouped so a host can place them in a header. */
export function ScenarioSelect({ state, idPrefix = 'explorer' }: { state: ScenarioExplorerState; idPrefix?: string }) {
  const { routes, scene, selectObjective, selectScene } = state
  const objectiveId = `${idPrefix}-objective-select`
  const sceneId = `${idPrefix}-scene-select`
  return <div className="selection-control">
    <div className="objective-select-wrap">
      <label className="visually-hidden" htmlFor={objectiveId}>Evaluation objective</label>
      <select id={objectiveId} value={routes.objectiveId} onChange={event => selectObjective(event.target.value)}>
        {catalog.families.map(family => <optgroup key={family.id} label={family.label}>
          {catalog.objectives.filter(item => item.family === family.id).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </optgroup>)}
      </select>
      <Icon name="chevron" size={19} />
    </div>
    <div className="scene-select-wrap">
      <label htmlFor={sceneId}>Scene</label>
      <select id={sceneId} value={scene.id} onChange={event => selectScene(event.target.value)}>
        {routes.scenes.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      <Icon name="chevron" size={15} />
    </div>
  </div>
}

/** Context badge, caption, map, detail actions, and the guided explanation. */
export function ScenarioStage({ state }: { state: ScenarioExplorerState }) {
  const { scene, step, stepIndex, routes, explainButton, inspect, goToStep, startWalkthrough, endWalkthrough } = state
  return <>
    <div className="context-bar">
      <button className={`scope-badge ${scene.status === 'target' ? 'is-target' : ''}`} onClick={() => inspect({ kind: 'scene' })}>
        <span className="scope-dot" />
        {scene.status === 'target' ? 'Target architecture' : scene.status === 'component' ? 'Component preview' : 'Architecture preview'}
        <Icon name="info" size={14} />
      </button>
      <span className="context-hint">
        <span className="desktop-hint">{step ? 'Guided explanation' : 'Explore the expected route'}</span>
        <span className="mobile-hint">{step ? 'Following each step' : 'Swipe to explore the map'}</span>
      </span>
    </div>
    <div className="scene-caption" aria-live="polite"><p>{scene.summary}</p></div>
    <div className="map-stage">
      <Graph key={`${routes.objectiveId}:${scene.id}`} scene={scene} step={step} onSelect={inspect} />
    </div>

    <div className="exploration-controls">
      <div className="detail-actions">
        <button className="text-button" onClick={() => inspect({ kind: 'scene' })}><Icon name="input" size={19} />Scene inputs</button>
        <button className="text-button" onClick={() => inspect({ kind: 'criteria' })}><Icon name="checklist" size={19} />What this tests</button>
      </div>
      <button ref={explainButton} className="primary-button" onClick={startWalkthrough} aria-expanded={stepIndex !== null}>
        <Icon name="play" size={19} />Explain step by step
      </button>
    </div>

    {step && stepIndex !== null && <section className="walkthrough" aria-label="Guided explanation">
      <div className="walkthrough-top">
        <span>Step {stepIndex + 1} of {scene.steps.length}</span>
        <button className="icon-button" onClick={endWalkthrough} aria-label="Exit explanation"><Icon name="close" size={20} /></button>
      </div>
      <div className="walkthrough-copy" aria-live="polite" aria-atomic="true"><h2>{step.title}</h2><p>{step.description}</p></div>
      <div className="walkthrough-bottom">
        <div className="step-dots" aria-hidden="true">
          {scene.steps.map((item, index) => <span key={item.title} className={index === stepIndex ? 'current' : index < stepIndex ? 'previous' : ''} />)}
        </div>
        <div className="step-actions">
          <button className="icon-button" aria-label="Previous step" disabled={stepIndex === 0} onClick={() => goToStep(Math.max(0, stepIndex - 1))}><Icon name="back" size={20} /></button>
          {stepIndex === scene.steps.length - 1
            ? <button className="next-button" onClick={endWalkthrough}>Finish<Icon name="close" size={17} /></button>
            : <button className="next-button" onClick={() => goToStep(stepIndex + 1)}>Next<Icon name="forward" size={17} /></button>}
        </div>
      </div>
    </section>}
  </>
}
