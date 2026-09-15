import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { playableScenarios } from '@linger/architecture-map'
import { SavedEvaluation } from './SavedEvaluation'

/**
 * Renders against the committed snapshot, so a scenario whose shape the panel
 * cannot handle fails here rather than in front of an audience.
 */
describe('SavedEvaluation', () => {
  const html = renderToStaticMarkup(<SavedEvaluation onClose={() => {}} />)

  it('says what it is before showing any jargon', () => {
    expect(html).toContain('You are reading a saved evaluation')
    expect(html).toContain('Not a live conversation')
  })

  it('shows the persona and what was placed in the account', () => {
    const scenario = playableScenarios[0]
    expect(html).toContain('invented persona')
    // The persona context is quoted from the backstory, not paraphrased.
    expect(html).toContain(scenario.persona.context.slice(0, 40))
  })

  it('frames the run set as distinct builds rather than repeated trials', () => {
    expect(html).toContain('recorded runs')
    expect(html).toContain('distinct build')
    expect(html).toContain('grouped by score, not a timeline')
  })

  it('renders the fixed line and says why it cannot be edited', () => {
    expect(html).toContain('The fixed message')
    expect(html).toContain('unbind the answer key')
  })

  it('draws the map and the key it was graded against', () => {
    expect(html).toContain('collaboration-graph')
    expect(html).toContain('What the key asked')
    expect(html).toContain('How to read a miss')
  })

  it('renders every scenario and run without throwing', () => {
    for (const scenario of playableScenarios) {
      expect(scenario.runs.length).toBeGreaterThan(0)
      for (const run of scenario.runs) {
        expect(run.scenes.length).toBeGreaterThan(0)
      }
    }
  })
})
