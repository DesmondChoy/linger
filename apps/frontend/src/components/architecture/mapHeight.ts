/** The map height a viewer chose, kept in this browser only. */

const STORAGE_KEY = 'linger.mapHeight'

/** The map height this viewer last chose, or null for the default. */
export function storedMapHeight(): number | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    const value = stored === null ? Number.NaN : Number(stored)
    return Number.isFinite(value) && value >= 0 ? value : null
  } catch {
    return null
  }
}

export function storeMapHeight(height: number | null) {
  try {
    if (height === null) window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, String(Math.round(height)))
  } catch {
    // A remembered height is a convenience; the default still works without it.
  }
}
