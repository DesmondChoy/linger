import { describe, expect, it } from 'vitest'

import { formatMachineLabel } from './formatMachineLabel'

describe('formatMachineLabel', () => {
  it('formats every segment of a multiword failure stage', () => {
    expect(formatMachineLabel('emotional_boundary_preflight')).toBe('emotional boundary preflight')
  })
})
