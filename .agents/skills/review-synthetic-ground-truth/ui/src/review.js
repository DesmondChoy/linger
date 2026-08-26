export function toggleId(ids, id) {
  const next = new Set(ids)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

export function reviewProgress(rows, reviewedIds) {
  const known = new Set(rows.map((row) => row.proposalId))
  const reviewed = [...reviewedIds].filter((id) => known.has(id)).length
  return {
    reviewed,
    total: rows.length,
    complete: rows.length > 0 && reviewed === rows.length,
  }
}

export function decisionPayload(action, reviewedIds, flaggedIds) {
  return {
    action,
    reviewedProposalIds: [...reviewedIds],
    flaggedProposalIds: [...flaggedIds],
  }
}
