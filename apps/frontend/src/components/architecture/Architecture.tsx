import { useMemo, useState } from 'react'
import { Graph, Icon, Inspector } from '@linger/architecture-map'
import type { InspectorSelection } from '@linger/architecture-map'
import type { ProgressEvent, TurnRecord } from '../../types'
import { formatMachineLabel } from '../formatMachineLabel'
import { buildLiveTurn } from './liveScene'

type Props = {
  timeline: TurnRecord[]
  /** Stages observed so far for a turn that is still running. */
  progress: ProgressEvent[]
  pendingMessage: string | null
}

function LiveTurnView({ timeline, progress, pendingMessage }: Props) {
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null)
  const [selection, setSelection] = useState<InspectorSelection | null>(null)

  // A running turn always wins the view; otherwise show the chosen completed
  // turn, defaulting to the most recent one.
  const live = pendingMessage !== null
  const index = live ? null : Math.min(selectedTurn ?? timeline.length - 1, timeline.length - 1)
  const turn = index === null || index < 0 ? undefined : timeline[index]

  const { scene, activity, active, running } = useMemo(() => buildLiveTurn({
    events: live ? progress : turn?.progress ?? [],
    userMessage: live ? pendingMessage : turn?.inspection.muse_turn.user_message ?? '',
    turn,
  }), [live, progress, pendingMessage, turn])

  if (!live && !turn) {
    return <div className="live-empty">
      <Icon name="serendipity" size={40} />
      <h3>No turn to map yet</h3>
      <p>
        Send a message. The map then rebuilds that turn from the server's content-free progress
        stream, showing which agents ran, which sources they were allowed to reach, and where the
        reply was released.
      </p>
      <p className="subtle">Or open a saved evaluation from the tray to read a run that already happened.</p>
    </div>
  }

  return <>
    <div className="live-bar">
      <span className={`live-status ${running ? 'is-running' : 'is-settled'}`}>
        <span className="live-dot" />
        {running ? 'Turn in progress' : 'Observed run'}
      </span>
      {!live && timeline.length > 1 && <label className="turn-picker">
        Turn
        <select
          value={index ?? 0}
          onChange={(event) => setSelectedTurn(Number(event.target.value))}
        >
          {timeline.map((item, position) => (
            <option key={item.inspection.muse_turn.turn_id} value={position}>
              {String(position + 1).padStart(2, '0')} · {item.inspection.muse_turn.user_message.slice(0, 44)}
            </option>
          ))}
        </select>
      </label>}
    </div>

    <div className="scene-caption" aria-live="polite"><p>{scene.summary}</p></div>
    <div className="map-stage">
      <Graph
        key={scene.id}
        scene={scene}
        step={active}
        onSelect={setSelection}
        description={running ? 'this turn as it runs' : 'observed route for this turn'}
      />
    </div>

    <section className="live-activity" aria-label="Components this turn used">
      <h4>What ran, in order</h4>
      <ul>
        {activity.map((item) => (
          <li key={item.id} className={item.status}>
            <b>{item.id.replaceAll('_', ' ')}</b>
            <span className={`trace-status ${item.status}`}>{formatMachineLabel(item.status)}</span>
            <small>{item.stages.map((stage) => formatMachineLabel(stage.stage)).join(' · ')}</small>
          </li>
        ))}
        {activity.length === 0 && <li className="running"><b>waiting</b><small>No stage has been reported yet.</small></li>}
      </ul>
      <p className="muted">
        Click any component or connection for its role, its bounded handoff, and who holds authority.
      </p>
    </section>

    <Inspector selection={selection} scene={scene} onClose={() => setSelection(null)} />
  </>
}

/**
 * The collaboration map beside the chat, rebuilt from the turn that just ran.
 *
 * Curated scenario browsing lives in the standalone evaluation explorer; this
 * surface only ever shows something that actually happened.
 */
export function Architecture(props: Props) {
  return <div className="architecture-map architecture-panel">
    <LiveTurnView {...props} />
  </div>
}
