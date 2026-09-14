export function selectionError(selectedIds, constraints) {
  if (selectedIds.length === 0) return 'Select at least one evaluation objective.'

  for (const constraint of constraints) {
    if (
      constraint.requiresAnyOtherObjective &&
      selectedIds.length === 1 &&
      selectedIds[0] === constraint.objectiveId
    ) {
      return constraint.reason
    }
  }

  return null
}

// A pairing counts in both directions: the catalog records it on one objective,
// on the other, or on both.
export function suggestedObjectiveIds(selectedIds, objectives) {
  const selected = new Set(selectedIds)
  const suggested = new Set()

  for (const objective of objectives) {
    if (selected.has(objective.id)) {
      for (const partnerId of objective.combinesWellWith) {
        if (!selected.has(partnerId)) suggested.add(partnerId)
      }
      continue
    }
    if (objective.combinesWellWith.some((partnerId) => selected.has(partnerId))) {
      suggested.add(objective.id)
    }
  }

  return suggested
}
