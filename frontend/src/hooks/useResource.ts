import { useEffect, useState } from 'react'
import { request } from '../lib/api'

export function useResource<T>(path: string | null, interval = 0) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ key: string; data?: T; error?: string } | null>(null)
  const key = `${path}:${revision}`
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    let busy = false
    async function load() {
      if (busy) return
      busy = true
      try {
        const data = await request<T>(path!, { signal: controller.signal })
        if (!controller.signal.aborted) setResult({ key, data })
      } catch (error) {
        if (!controller.signal.aborted) setResult({ key, error: error instanceof Error ? error.message : 'Request failed' })
      } finally { busy = false }
    }
    void load()
    const timer = interval ? window.setInterval(load, interval) : null
    return () => { controller.abort(); if (timer) window.clearInterval(timer) }
  }, [path, interval, key])
  const current = result?.key === key ? result : null
  return { data: current?.data, error: current?.error, loading: !!path && !current, refresh: () => setRevision(value => value + 1) }
}
