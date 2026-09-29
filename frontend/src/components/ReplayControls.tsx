import { useState } from 'react'
import { pauseReplay, playReplay, resetReplay, setReplaySpeed, request } from '../lib/api'
import type { ReplayStatus } from '../lib/api'
import { useRaceStore } from '../stores/raceStore'
import type { Analysis } from '../types/analysis'

export function ReplayControls({ analysis }: { analysis?: Analysis }) {
  const { sessionKey, playing, speed, state } = useRaceStore()
  const [drag, setDrag] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  if (!sessionKey) return null
  const key = sessionKey
  const start = analysis ? Date.parse(analysis.start) : 0
  const end = analysis ? Date.parse(analysis.end) : 0
  const current = state ? Date.parse(state.replay_timestamp) : start
  const length = Math.max(0, (end - start) / 1000)
  const elapsed = Math.max(0, (current - start) / 1000)
  function applyStatus(status: ReplayStatus) {
    if (!status.state) return
    useRaceStore.getState().applyRealtimeState({
      revision: status.revision ?? 0,
      event_index: status.event_index,
      total_events: status.total_events,
      playing: status.playing,
      speed: status.speed,
      state: status.state,
    })
  }
  async function run(action: () => Promise<ReplayStatus>) {
    setBusy(true); setMessage('')
    try { applyStatus(await action()) } catch (e) { setMessage(String(e)) } finally { setBusy(false) }
  }
  function seek(seconds: number) {
    return run(() => request<ReplayStatus>(`/replay/${key}/seek/time`, { method: 'POST', body: JSON.stringify({ timestamp: new Date(start + seconds * 1000).toISOString() }) }))
  }
  function commit() { if (drag !== null) void seek(drag).finally(() => setDrag(null)) }
  async function bookmark() {
    const url = new URL(window.location.href)
    url.searchParams.set('session', String(key))
    if (state) url.searchParams.set('time', state.replay_timestamp)
    url.searchParams.set('driver', useRaceStore.getState().selectedDriver)
    try { await navigator.clipboard.writeText(url.toString()); setMessage('Race moment copied') }
    catch { setMessage(`Bookmark: ${url}`) }
  }
  return <section className="replay-controls" aria-label="Replay controls">
    <div className="control-buttons"><button className="primary-button" disabled={busy || !state} onClick={() => void run(() => playing ? pauseReplay(key) : playReplay(key))}>{playing ? 'Ⅱ Pause' : '▶ Play'}</button><button disabled={busy || !state} onClick={() => void run(() => resetReplay(key))}>↺ Reset</button></div>
    <label className="speed-control">Speed <select aria-label="Replay speed" disabled={busy} value={speed} onChange={e => void run(() => setReplaySpeed(key, Number(e.target.value)))}>{[1, 5, 10, 25, 50, 100].map(s => <option value={s} key={s}>{s}×</option>)}</select></label>
    <div className="timeline"><input aria-label="Replay time in seconds" type="range" min={0} max={length} step={0.1} value={drag ?? Math.min(elapsed, length)} disabled={busy || !length} onChange={e => setDrag(Number(e.target.value))} onPointerUp={commit} onKeyUp={commit} onPointerCancel={() => setDrag(null)} /><span>{Math.floor((drag ?? elapsed) / 60)}:{String(Math.floor((drag ?? elapsed) % 60)).padStart(2, '0')} / {Math.floor(length / 60)}m</span></div>
    <select aria-label="Jump to lap" value="" disabled={busy || !analysis} onChange={e => void seek(Number(e.target.value))}><option value="">Jump to lap…</option>{analysis?.laps.filter(l => l.driver === useRaceStore.getState().selectedDriver).map(l => <option key={l.lap} value={(Date.parse(l.start) - start) / 1000}>Lap {l.lap}</option>)}</select>
    <button onClick={() => void bookmark()} disabled={!state}>↗ Share moment</button>
    {message && <p role="status" className="control-feedback">{message}</p>}
  </section>
}
