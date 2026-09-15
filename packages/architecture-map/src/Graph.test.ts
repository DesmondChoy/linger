import { describe, expect, it } from 'vitest'
import { anchor } from './Graph'

/**
 * The hover card is positioned against the viewport rather than the canvas,
 * because the canvas lives inside an `overflow: auto` scroller that clipped it.
 */
function rect(values: Partial<DOMRect>): DOMRect {
  return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}), ...values } as DOMRect
}

describe('hover card placement', () => {
  const viewport = { innerWidth: 1400, innerHeight: 900 }
  Object.assign(globalThis, { window: viewport })

  it('escapes the scrolling canvas by positioning against the viewport', () => {
    expect(anchor(rect({ left: 600, width: 180, bottom: 300, top: 120 })).position).toBe('fixed')
  })

  it('sits below the component when there is room', () => {
    const style = anchor(rect({ left: 600, width: 180, bottom: 300, top: 120 }))
    expect(style.top).toBe(310)
    expect(style.transform).toBe('translateX(-50%)')
  })

  it('flips above when the component is near the bottom of the window', () => {
    const style = anchor(rect({ left: 600, width: 180, bottom: 800, top: 620 }))
    expect(style.top).toBe(610)
    expect(style.transform).toBe('translate(-50%, -100%)')
  })

  it('keeps a card near either edge fully on screen', () => {
    expect(anchor(rect({ left: 0, width: 40, bottom: 200 })).left).toBe(175)
    expect(anchor(rect({ left: 1390, width: 10, bottom: 200 })).left).toBe(1225)
  })
})
