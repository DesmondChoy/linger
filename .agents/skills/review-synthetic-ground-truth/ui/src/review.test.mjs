import assert from 'node:assert/strict'
import test from 'node:test'
import { decisionPayload, reviewProgress, toggleId } from './review.js'

const rows = [{ proposalId: 'proposal-1' }, { proposalId: 'proposal-2' }]

test('review progress completes only after every proposal is checked', () => {
  assert.deepEqual(reviewProgress(rows, new Set()), {
    reviewed: 0,
    total: 2,
    complete: false,
  })
  assert.equal(reviewProgress(rows, new Set(['proposal-1'])).complete, false)
  assert.equal(
    reviewProgress(rows, new Set(['proposal-1', 'proposal-2'])).complete,
    true,
  )
})

test('toggle and decision payload preserve explicit proposal identities', () => {
  const reviewed = toggleId(new Set(['proposal-1']), 'proposal-2')
  const flagged = toggleId(new Set(), 'proposal-1')
  assert.deepEqual(decisionPayload('make_changes', reviewed, flagged), {
    action: 'make_changes',
    reviewedProposalIds: ['proposal-1', 'proposal-2'],
    flaggedProposalIds: ['proposal-1'],
  })
})
