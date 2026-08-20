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
