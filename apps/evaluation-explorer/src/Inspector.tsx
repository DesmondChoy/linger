import { useEffect, useRef, useState } from 'react'
import { Icon } from './Icon'
import catalog from './catalog.json'
import { components } from './scenarios'
import type { InspectorSelection, Scene } from './types'

export type Objective = typeof catalog.objectives[number]

function DetailList({ title, items }: { title: string; items: string[] }) {
  return <section className="detail-section"><h3>{title}</h3><ul>{items.map(item => <li key={item}>{item}</li>)}</ul></section>
}

function History({ objective }: { objective: Objective }) {
  const [showAll, setShowAll] = useState(false)
  const packages = catalog.packages.filter(item => showAll || item.objectiveIds.includes(objective.id))
  return <>
    <p className="drawer-intro">Generated packages and recorded runs from the repository.</p>
    <label className="archive-filter"><input type="checkbox" checked={showAll} onChange={event => setShowAll(event.target.checked)} /> Show all objectives</label>
    <p className="subtle">{showAll ? 'All objectives' : objective.title} · {packages.length} {packages.length === 1 ? 'package' : 'packages'}</p>
    {packages.length === 0 && <div className="empty-state"><Icon name="history" size={36} /><h3>No generated package yet</h3><p>This objective can be explored as an architecture preview. Generation and evaluation remain separate work.</p></div>}
    {packages.map(item => <details className="archive-package" key={item.id}>
      <summary><span><strong>{item.id.slice(0, 10)}</strong><small>{item.sceneCount} Scenes · {item.runs.length} recorded {item.runs.length === 1 ? 'file' : 'files'}</small></span><Icon name="chevron" size={18} /></summary>
      <div className="archive-body">
        <p>{item.objectiveIds.map(id => catalog.objectives.find(value => value.id === id)?.title ?? id).join(', ')}</p>
        <p className="record-note">{item.adoptionRecorded ? 'Ground truth adoption record present.' : 'No Ground truth adoption record in this package.'}</p>
        <small className="source-path">synthetic-journal-evaluation/packages/{item.id}</small>
        {item.runs.length === 0 && <p className="subtle">No replay artifact stored in this folder.</p>}
        {item.runs.map(run => <details className="archive-run" key={run.file}>
          <summary>{run.file}</summary>
          <p className="subtle">{run.kind === 'summary' ? 'Saved summary' : 'Saved artifact'}. Run <span className="run-id">{run.runId}</span></p>
          <ul className="run-scenes">{run.scenes.map((scene, index) => <li key={`${scene.id}-${index}`}><strong>{scene.id}</strong><span>{scene.result.replaceAll('_', ' ')}</span>{scene.failures.length > 0 && <small>{scene.failures.join(', ').replaceAll('_', ' ')}</small>}</li>)}</ul>
        </details>)}
      </div>
    </details>)}
    <p className="evidence-note">These are archived file records, not a fresh evaluation. Record presence does not revalidate adoption hashes or semantic quality. The map continues to show the selected Scene’s expected route.</p>
  </>
}

function InspectorContent({ selection, scene, objective }: { selection: InspectorSelection; scene: Scene; objective: Objective }) {
  switch (selection.kind) {
    case 'node': {
      const component = components[selection.id]
      return <>
        <div className={`inspector-glyph kind-${component.kind}`}><Icon name={component.id} size={36} /></div>
        <p className="detail-kind">{component.kind === 'agent' ? 'Reasoning agent' : component.kind === 'service' ? 'Deterministic service' : component.kind === 'source' ? 'Source or context' : 'Workflow output'}</p>
        <p className="drawer-intro">{component.summary}</p>
        <DetailList title="Receives" items={component.receives} />
        <DetailList title="Returns" items={component.returns} />
        <section className="authority-note"><h3>Who has authority</h3><p>{component.authority}</p></section>
        <p className="evidence-note">The application constructs and passes each bounded handoff. A connector describes that exchange, not a direct agent-to-agent channel.</p>
      </>
    }
    case 'edge': {
      const edge = scene.edges.find(value => value.id === selection.id)
      if (!edge) return null
      return <>
        <div className="handoff-pair"><span>{components[edge.source].label}</span><Icon name="arrow" size={22} /><span>{components[edge.target].label}</span></div>
        <p className="drawer-intro">{edge.summary}</p>
        <DetailList title="What crosses this boundary" items={edge.payload} />
        <section className="authority-note"><h3>Application-controlled handoff</h3><p>The application owns transport, scope and orchestration. Receiving a proposal does not grant permission to release a response or write a memory.</p></section>
      </>
    }
    case 'scene':
      return <>
        <p className="drawer-intro">{scene.summary}</p>
        <section className="scene-example"><span>{scene.input.title}</span><p>{scene.input.text}</p><small>Illustrative input for this explanation, not a generated package or recorded run.</small></section>
        <section className="detail-section"><h3>Implementation scope</h3><p>{scene.statusNote}</p></section>
        <DetailList title="Expected behavior" items={scene.expected} />
      </>
    case 'criteria':
      return <>
        <p className="drawer-intro">{objective.summary}</p>
        <DetailList title="In this Scene" items={scene.expected} />
        <details className="more-detail"><summary>Complete objective criteria</summary><DetailList title="Observable outcomes" items={objective.criteria} /></details>
        <details className="more-detail"><summary>Suggested measures</summary><ul className="measure-list">{objective.measures.map(item => <li key={item}>{item.replaceAll('_', ' ')}</li>)}</ul></details>
        <details className="more-detail"><summary>Academic contribution</summary><DetailList title="What this demonstrates" items={objective.academicValue} /></details>
        <p className="evidence-note">Ground truth belongs to the evaluator and never enters an agent’s context. A preview explains what should happen; it does not measure these outcomes.</p>
      </>
    case 'history': return <History objective={objective} />
    case 'about': return <>
      <p className="drawer-intro">One system. Distinct responsibilities.</p>
      <p>Linger’s agents reason about different parts of a reflection. The application brings their work together and retains control of every handoff.</p>
      <div className="role-key"><span className="key-agent" /> Reasoning agents <span className="key-service" /> Deterministic services</div>
      <div className="agent-directory">{(['muse', 'librarian', 'provenance', 'sculptor', 'serendipity'] satisfies (keyof typeof components)[]).map(id => <div key={id}><Icon name={id} size={26} /><span><strong>{components[id].label}</strong><small>{components[id].summary}</small></span></div>)}</div>
      <section className="authority-note"><h3>Reasoning and authority are separate</h3><p>Muse drafts. Provenance reviews. Deterministic release checks decide what can leave the system. Memory & Policy owns durable writes; Sculptor can propose changes.</p></section>
      <section className="detail-section"><h3>How to explore</h3><p>Choose an objective and a Scene. Hover for a short explanation, or select a component or connection for details. “Explain step by step” highlights each expected handoff. Use the arrow keys during an explanation and Escape to exit.</p></section>
      <p className="evidence-note">Architecture previews use maintained catalog and source contracts. This separate frontend does not call agents or start evaluations. Sources: docs/specification.md and {catalog.catalogSource}.</p>
    </>
    default: {
      const exhaustive: never = selection
      return exhaustive
    }
  }
}

export function Inspector({ selection, scene, objective, onClose }: { selection: InspectorSelection | null; scene: Scene; objective: Objective; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (selection && !dialog.current?.open) dialog.current?.showModal()
    if (!selection && dialog.current?.open) dialog.current.close()
  }, [selection])
  let title = 'About this explorer'
  if (selection?.kind === 'node') title = scene.nodes.find(node => node.id === selection.id)?.label ?? components[selection.id].label
  if (selection?.kind === 'edge') title = scene.edges.find(edge => edge.id === selection.id)?.label || 'A bounded handoff'
  if (selection?.kind === 'scene') title = scene.title
  if (selection?.kind === 'criteria') title = 'What this tests'
  if (selection?.kind === 'history') title = 'History'
  return <dialog ref={dialog} className="inspector" aria-labelledby="inspector-title" onCancel={onClose} onClose={onClose} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose() } }}>
    <header className="inspector-header"><h2 id="inspector-title">{title}</h2><button className="icon-button" aria-label="Close details" onClick={onClose} autoFocus><Icon name="close" /></button></header>
    <div className="inspector-content">{selection && <InspectorContent key={`${selection.kind}-${'id' in selection ? selection.id : ''}`} selection={selection} scene={scene} objective={objective} />}</div>
  </dialog>
}
