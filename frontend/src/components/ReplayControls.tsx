import { useEffect, useRef, useState } from 'react'
import { pauseReplay, playReplay, resetReplay, setReplaySpeed, request } from '../lib/api'
import type { ReplayStatus } from '../lib/api'
import { useRaceStore } from '../stores/raceStore'
import type { Analysis } from '../types/analysis'

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

function firstRecordedLap(analysis?: Analysis) {
  if (!analysis) return 0
  const sessionStart = Date.parse(analysis.start)
  const lapStarts = analysis.laps
    .map(lap => Date.parse(lap.start))
    .filter(timestamp => Number.isFinite(timestamp))
  return lapStarts.length ? Math.max(sessionStart, Math.min(...lapStarts)) : sessionStart
}

export function ReplayControls({ analysis }: { analysis?: Analysis }) {
  const { sessionKey, playing, speed, state } = useRaceStore()
  const [drag, setDrag] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const aligning = useRef('')
  const start = firstRecordedLap(analysis)
  const end = analysis ? Date.parse(analysis.end) : 0
  const current = state ? Date.parse(state.replay_timestamp) : start
  const length = Math.max(0, (end - start) / 1000)
  const elapsed = Math.max(0, (current - start) / 1000)

  // Providers often open a session well before cars begin a recorded lap.
  // Start at the first usable lap so telemetry and map markers are visible
  // immediately instead of replaying a long empty pre-session interval.
  useEffect(() => {
    if (!sessionKey || !start) return
    if (current >= start) {
      aligning.current = ''
      return
    }
    const alignment = `${sessionKey}:${start}`
    if (aligning.current === alignment) return
    aligning.current = alignment
    let cancelled = false
    request<ReplayStatus>(`/replay/${sessionKey}/seek/time`, {
      method: 'POST',
      body: JSON.stringify({ timestamp: new Date(start).toISOString() }),
    })
      .then(status => { if (!cancelled) applyStatus(status) })
      .catch(error => {
        aligning.current = ''
        if (!cancelled) setMessage(String(error))
      })
    return () => { cancelled = true }
  }, [current, sessionKey, start])

  if (!sessionKey) return null
  const key = sessionKey

  async function run(action: () => Promise<ReplayStatus>) {
    setBusy(true)
    setMessage('')
    try {
      applyStatus(await action())
    } catch (error) {
      setMessage(String(error))
    } finally {
      setBusy(false)
    }
  }

  function seek(seconds: number) {
    return run(() => request<ReplayStatus>(`/replay/${key}/seek/time`, {
      method: 'POST',
      body: JSON.stringify({ timestamp: new Date(start + seconds * 1000).toISOString() }),
    }))
  }

  function commit() {
    if (drag !== null) void seek(drag).finally(() => setDrag(null))
  }

  async function bookmark() {
    const url = new URL(window.location.href)
    url.searchParams.set('session', String(key))
    if (state) url.searchParams.set('time', state.replay_timestamp)
    url.searchParams.set('driver', useRaceStore.getState().selectedDriver)
    try {
      await navigator.clipboard.writeText(url.toString())
      setMessage('Race moment copied')
    } catch {
      setMessage(`Bookmark: ${url}`)
    }
  }

  return <section className="replay-controls" aria-label="Replay controls">
    <div className="control-buttons"><button className="primary-button" disabled={busy || !state} onClick={() => void run(() => playing ? pauseReplay(key) : playReplay(key))}>{playing ? 'Ⅱ Pause' : '▶ Play'}</button><button disabled={busy || !state} onClick={() => void run(() => resetReplay(key))}>↺ Reset</button></div>
    <label className="speed-control">Speed <select aria-label="Replay speed" disabled={busy} value={speed} onChange={event => void run(() => setReplaySpeed(key, Number(event.target.value)))}>{[1, 5, 10, 25, 50, 100].map(value => <option value={value} key={value}>{value}×</option>)}</select></label>
    <div className="timeline"><input aria-label="Replay time in seconds" type="range" min={0} max={length} step={0.1} value={drag ?? Math.min(elapsed, length)} disabled={busy || !length} onChange={event => setDrag(Number(event.target.value))} onPointerUp={commit} onKeyUp={commit} onPointerCancel={() => setDrag(null)} /><span>{Math.floor((drag ?? elapsed) / 60)}:{String(Math.floor((drag ?? elapsed) % 60)).padStart(2, '0')} / {Math.floor(length / 60)}m</span></div>
    <select aria-label="Jump to lap" value="" disabled={busy || !analysis} onChange={event => void seek(Number(event.target.value))}><option value="">Jump to lap…</option>{analysis?.laps.filter(lap => lap.driver === useRaceStore.getState().selectedDriver).map(lap => <option key={lap.lap} value={(Date.parse(lap.start) - start) / 1000}>Lap {lap.lap}</option>)}</select>
    <button onClick={() => void bookmark()} disabled={!state}>↗ Share moment</button>
    {message && <p role="status" className="control-feedback">{message}</p>}
  </section>
}
