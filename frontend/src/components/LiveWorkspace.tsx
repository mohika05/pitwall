import { TrackMap } from "./TrackMap"
import { useEffect, useState } from 'react'
import { useResource } from '../hooks/useResource'
import { request } from '../lib/api'
import type { RaceState } from '../types/race'
import type { TelemetrySnapshot, TrackShape } from '../types/telemetry'

interface LiveFeed { track?: TrackShape; session_key: number; status: string; state: RaceState | null; telemetry: TelemetrySnapshot | null; updated_at: string | null; error: string | null }
export function LiveWorkspace({ sessionKey }: { sessionKey: number | null }) {
  const [key, setKey] = useState(sessionKey ?? 0)
  const [input, setInput] = useState(String(sessionKey ?? ''))
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const feed = useResource<LiveFeed>(key ? `/live/${key}` : null, 2000)
  async function command(action: 'start' | 'stop') {
    setBusy(true); setError('')
    try {
      const selected = Number(input)
      await request(`/live/${selected}/${action}`, { method: 'POST' })
      setKey(selected); feed.refresh()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  return <div className="workspace-stack"><div className="workspace-heading"><div><span className="eyebrow">LIVE TIMING</span><h2>The session, as it unfolds.</h2></div><span className={`mode-badge ${feed.data?.status === 'live' ? 'live' : ''}`}>{feed.data?.status ?? 'OFFLINE'}</span></div>
    <section className="panel live-controls"><label>OpenF1 session ID<input type="number" min={1} value={input} onChange={e => setInput(e.target.value)} /></label><button className="primary-button" disabled={busy || !Number(input)} onClick={() => void command('start')}>Connect live feed</button><button disabled={busy || !key} onClick={() => void command('stop')}>Stop feed</button><p className="panel-note">Live mode requires provider access configured on the server. Updates arrive in polling batches; sample timestamps show their age. Historical replay remains independent.</p></section>
    {(error || feed.error || feed.data?.error) && <p role="alert" className="control-error">{error || feed.error || feed.data?.error}</p>}
    <section className="panel"><div className="panel-title">Live running order <span>Updated {feed.data?.updated_at ? new Date(feed.data.updated_at).toLocaleTimeString() : '—'}</span></div><div className="table-scroll"><table><thead><tr><th>Pos</th><th>Driver</th><th>Lap</th><th>Tyre</th><th>Gap</th><th>Speed</th><th>Gear</th><th>Throttle</th><th>Sample age</th></tr></thead><tbody>{Object.values(feed.data?.state?.drivers ?? {}).sort((a, b) => (a.position ?? 99) - (b.position ?? 99)).map(d => {
      const telemetry = feed.data?.telemetry?.drivers.find(t => t.driver_number === d.driver_number)
      const age = telemetry?.car?.Date ? (now - Date.parse(telemetry.car.Date)) / 1000 : null
      return <tr key={d.driver_number}><td>{d.position ?? '—'}</td><td>{d.name_acronym}</td><td>{d.current_lap}</td><td>{d.compound}</td><td>{d.gap_to_leader ?? '—'}</td><td>{telemetry?.car?.Speed ?? '—'}</td><td>{telemetry?.car?.nGear ?? '—'}</td><td>{telemetry?.car?.Throttle ?? '—'}%</td><td>{age == null ? 'Missing' : `${Math.max(0, age).toFixed(0)}s`}</td></tr>
    })}</tbody></table></div>{!feed.data?.state && <p className="empty-state">Connect a session to receive its timing and telemetry.</p>}</section>
    {feed.data?.state && feed.data.telemetry && <TrackMap key={key} session={key} liveState={feed.data.state} liveTelemetry={feed.data.telemetry} referenceTrack={feed.data.track} />}
    <section className="panel"><div className="panel-title">Race control</div><p className="panel-note">{feed.data?.state?.latest_race_control_message ?? 'No message received.'}</p></section>
  </div>
}
