// Tab-scoped identity separates playback while allowing reload recovery.
const key = "pitwall.viewer"
let id: string | null = null
export function viewerId(): string {
  if (id) return id
  try {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    // Duplicating a tab clones sessionStorage; only an actual reload reuses it.
    id = (navigation?.type === 'reload' ? sessionStorage.getItem(key) : null) || crypto.randomUUID()
    sessionStorage.setItem(key, id)
  } catch {
    id = crypto.randomUUID()
  }
  return id
}
