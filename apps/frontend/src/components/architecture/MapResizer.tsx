import { useRef, type KeyboardEvent, type PointerEvent, type RefObject } from 'react'
import { storeMapHeight } from './mapHeight'

const KEY_STEP = 32
/** At its tallest the map still leaves this much of the panel to the turn record. */
const RECORD_RESERVE = 200

type Props = {
  height: number | null
  onChange: (height: number | null) => void
  /** The visible map, measured when a resize starts. */
  stage: RefObject<HTMLElement | null>
  /** The whole panel, which bounds how tall the map may grow. */
  panel: RefObject<HTMLElement | null>
}

/** A drag handle between the map and the turn record; double-click restores the default. */
export function MapResizer({ height, onChange, stage, panel }: Props) {
  const drag = useRef<{ startY: number; startHeight: number } | null>(null)

  const measured = () => stage.current?.getBoundingClientRect().height ?? 0
  const resize = (next: number, remember: boolean) => {
    const maxHeight = Math.max(0, (panel.current?.clientHeight ?? 0) - RECORD_RESERVE)
    const clamped = Math.round(Math.min(Math.max(next, 0), maxHeight))
    onChange(clamped)
    if (remember) storeMapHeight(clamped)
  }

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { startY: event.clientY, startHeight: measured() }
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current) resize(drag.current.startHeight + event.clientY - drag.current.startY, false)
  }
  const onPointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    resize(drag.current.startHeight + event.clientY - drag.current.startY, true)
    drag.current = null
  }
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = {
      ArrowUp: measured() - KEY_STEP,
      ArrowDown: measured() + KEY_STEP,
      Home: 0,
      End: Number.POSITIVE_INFINITY,
    }[event.key]
    if (next === undefined) return
    event.preventDefault()
    resize(next, true)
  }

  return (
    <div
      className="map-resizer"
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize the map"
      aria-valuemin={0}
      aria-valuenow={height ?? undefined}
      tabIndex={0}
      title="Drag to resize the map. Double-click to reset."
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onKeyDown={onKeyDown}
      onDoubleClick={() => { onChange(null); storeMapHeight(null) }}
    >
      <span className="map-resizer-grip" />
    </div>
  )
}
