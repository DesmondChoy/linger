import {
  catalog,
  Icon,
  Inspector,
  ScenarioSelect,
  ScenarioStage,
  useScenarioExplorer,
} from '@linger/architecture-map'

export default function App() {
  const explorer = useScenarioExplorer()
  const { objective, scene } = explorer

  if (!objective) {
    return <main className="load-error">
      <h1>Objective unavailable</h1>
      <p>Refresh the repository catalog snapshot and restart the explorer.</p>
    </main>
  }

  return <div className={`architecture-map explorer ${explorer.stageClassName}`}>
    <header className="app-header">
      <a className="wordmark" href="./" aria-label="Linger evaluation explorer home">
        <span className="brand-mark"><span /><span /></span>Linger
        <span className="wordmark-detail">Evaluation explorer</span>
      </a>
      <ScenarioSelect state={explorer} />
      <nav className="header-actions" aria-label="Explorer">
        <button className="text-button history-button" onClick={() => explorer.inspect({ kind: 'history' })}>
          <Icon name="history" size={19} /><span>History</span>
        </button>
        <button className="icon-button" aria-label="About the explorer" onClick={() => explorer.inspect({ kind: 'about' })}>
          <Icon name="info" size={23} />
        </button>
      </nav>
    </header>

    <main className="workspace" id="main-content">
      <ScenarioStage state={explorer} />
    </main>

    <footer className="app-footer">
      <button onClick={() => explorer.inspect({ kind: 'about' })}>
        <span className="handoff-mark" />Application-controlled handoffs
      </button>
      <span>{catalog.objectives.length} objectives, distinct ways to collaborate</span>
    </footer>

    <Inspector
      selection={explorer.selection}
      scene={scene}
      objective={objective}
      onClose={explorer.closeInspector}
    />
  </div>
}
