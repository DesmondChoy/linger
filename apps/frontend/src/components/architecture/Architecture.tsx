import { useMemo, useState } from 'react'
import { Graph, Icon } from '@linger/architecture-map'
import type { ComponentId } from '@linger/architecture-map'
import type { ProgressEvent, TurnRecord } from '../../types'
import { formatMachineLabel } from '../formatMachineLabel'
import { Inspector } from '../Inspector'
import { buildLiveTurn } from './liveScene'
import { detailFor, type ComponentDetail } from './turnDetail'

type Props = {
  timeline: TurnRecord[]
  /** Stages observed so far for a turn that is still running. */
  progress: ProgressEvent[]
  pendingMessage: string | null
}

type Selection = { kind: 'node'; id: ComponentId } | { kind: 'edge'; id: string }

function DetailPanel({ detail, onClear }: { detail: ComponentDetail; onClear: () => void }) {
  return (
    <section className="component-detail" aria-live="polite">
      <div className="detail-top">
        <div>
          <p className="eyebrow">{detail.role}</p>
          <h3>{detail.title}</h3>
        </div>
        <button type="button" className="quiet-button" onClick={onClear}>Close</button>
      </div>
      <p className="detail-did">{detail.did}</p>

      {detail.records.map((record) => (
        <div className="detail-record" key={record.label}>
          <p className="detail-record-label">{record.label}</p>
          <pre>{typeof record.value === 'string' ? record.value : JSON.stringify(record.value, null, 2)}</pre>
        </div>
      ))}
      {detail.records.length === 0 && (
        <p className="muted">This turn recorded no data for this handoff.</p>
      )}

      <details className="raw-detail">
        <summary>What this component is, in general</summary>
        <dl className="standing-contract">
          {detail.receives.length > 0 && <><dt>Receives</dt><dd>{detail.receives.join(' · ')}</dd></>}
          {detail.returns.length > 0 && <><dt>Returns</dt><dd>{detail.returns.join(' · ')}</dd></>}
          <dt>Authority</dt><dd>{detail.authority}</dd>
        </dl>
      </details>
    </section>
  )
}

/**
 * The collaboration map and the turn's record, on one surface.
 *
 * The map stays put while the record scrolls beneath it, and selecting a
 * component replaces the record's head with that component's data for THIS
 * turn — the contract it actually carried, not a description of its role.
 */
export function Architecture({ timeline, progress, pendingMessage }: Props) {
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)

  const live = pendingMessage !== null
  const index = live ? null : Math.min(selectedTurn ?? timeline.length - 1, timeline.length - 1)
  const turn = index === null || index < 0 ? undefined : timeline[index]

  const { scene, activity, active, running } = useMemo(() => buildLiveTurn({
    events: live ? progress : turn?.progress ?? [],
    userMessage: live ? pendingMessage : turn?.inspection.muse_turn.user_message ?? '',
    turn,
  }), [live, progress, pendingMessage, turn])

  const detail = useMemo(
    () => (selection && turn ? detailFor(selection, scene, turn) : null),
    [selection, scene, turn],
  )

  if (!live && !turn) {
    return (
      <div className="architecture-map architecture-panel">
        <div className="live-empty">
          <Icon name="serendipity" size={40} />
          <h3>No turn to map yet</h3>
          <p>
            Send a message. The map then rebuilds that turn from the server's content-free progress
            stream, showing which agents ran, which sources they were allowed to reach, and where the
            reply was released.
          </p>
          <p className="subtle">Or open a saved evaluation from the tray to read a run that already happened.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="architecture-map architecture-panel">
      <div className="map-sticky">
        <div className="live-bar">
          <span className={`live-status ${running ? 'is-running' : 'is-settled'}`}>
            <span className="live-dot" />
            {running ? 'Turn in progress' : 'Observed run'}
          </span>
          {!live && timeline.length > 1 && (
            <label className="turn-picker">
              Turn
              <select
                value={index ?? 0}
                onChange={(event) => { setSelectedTurn(Number(event.target.value)); setSelection(null) }}
              >
                {timeline.map((item, position) => (
                  <option key={item.inspection.muse_turn.turn_id} value={position}>
                    {String(position + 1).padStart(2, '0')} · {item.inspection.muse_turn.user_message.slice(0, 44)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div className="scene-caption"><p>{scene.summary}</p></div>
        <div className="map-stage">
          <Graph
            key={scene.id}
            scene={scene}
            step={active}
            onSelect={(value) => {
              if (value.kind === 'node' || value.kind === 'edge') setSelection(value as Selection)
            }}
            description={running ? 'this turn as it runs' : 'observed route for this turn'}
          />
        </div>
      </div>

      <div className="analysis-detail">
        {detail ? (
          <DetailPanel detail={detail} onClear={() => setSelection(null)} />
        ) : (
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
              Click any component or connection above to see the contract it carried on this turn.
            </p>
          </section>
        )}

        {/* Every turn stays listed; the mapped one is opened and marked. */}
        <Inspector
          timeline={timeline}
          selectedTurnId={turn?.inspection.muse_turn.turn_id}
          onSelectTurn={(turnId) => {
            const position = timeline.findIndex((item) => item.inspection.muse_turn.turn_id === turnId)
            if (position >= 0) { setSelectedTurn(position); setSelection(null) }
          }}
        />
      </div>
    </div>
  )
}
