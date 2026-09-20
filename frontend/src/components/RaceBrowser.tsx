import { useEffect, useState } from 'react'
import { getCatalogYears, getSessions, request } from '../lib/api'
import { useRaceStore } from '../stores/raceStore'
import { useResource } from '../hooks/useResource'
import type { YearCatalogue, CatalogSession } from '../types/catalog'
import type { PreparationJob } from '../types/analysis'

export function RaceBrowser() {
  const sessionKey = useRaceStore(s => s.sessionKey)
  const setSession = useRaceStore(s => s.setSessionKey)
  const [years, setYears] = useState<number[]>([])
  const [year, setYear] = useState<number | null>(null)
  const [meeting, setMeeting] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const catalogue = useResource<YearCatalogue>(year ? `/catalog/${year}` : null)
  const jobs = useResource<PreparationJob[]>('/preparation', 3000)
  useEffect(() => {
    let stopped = false
    Promise.all([getCatalogYears(), getSessions()]).then(([available, local]) => {
      if (stopped) return
      setYears(available.years)
      const query = new URLSearchParams(window.location.search)
      const linked = Number(query.get('session'))
      const selected = local.sessions.find(s => s.session_key === linked) ?? local.sessions[0]
      setYear(selected?.year ?? available.years.at(-1) ?? null)
      if (selected && useRaceStore.getState().sessionKey === null) setSession(selected.session_key)
    }).catch(e => { if (!stopped) setError(String(e)) })
    return () => { stopped = true }
  }, [setSession])
  const meetings = catalogue.data?.meetings ?? []
  const selectedMeeting = meetings.find(m => m.meeting_key === meeting)
    ?? meetings.find(m => m.sessions.some(s => s.session_key === sessionKey)) ?? meetings[0]
  const selected = meetings.flatMap(m => m.sessions).find(s => s.session_key === sessionKey)
  async function choose(session: CatalogSession) {
    const job = jobs.data?.find(j => j.session_key === session.session_key)
    if (session.ingested || job?.events_ready) { setSession(session.session_key); return }
    setPending(session.session_key); setError(null)
    try {
      await request(`/preparation/${session.session_key}`, { method: 'POST', body: JSON.stringify({ telemetry: true }) })
      jobs.refresh()
    } catch (e) { setError(String(e)) }
    finally { setPending(null) }
  }
  return <section className="race-browser">
    <div className="race-browser-header">
      <div><span className="eyebrow">SESSION DIRECTORY</span><h2>{selectedMeeting?.meeting_name ?? 'Choose your Grand Prix'}</h2></div>
      <label className="season-control">Season <select aria-label="Season" value={year ?? ''} onChange={e => { setYear(Number(e.target.value)); setMeeting(null) }}>{years.map(y => <option key={y}>{y}</option>)}</select></label>
    </div>
    <details open={!sessionKey}>
      <summary>{selected?.session_name ?? 'Browse races and sessions'} <span className="muted">· Change session</span></summary>
      <div className="catalogue-tabs" aria-label="Grand Prix weekends">{meetings.map(m => <button key={m.meeting_key} className={selectedMeeting?.meeting_key === m.meeting_key ? 'active' : ''} onClick={() => setMeeting(m.meeting_key)}>{m.meeting_name?.replace(' Grand Prix', '') ?? m.location}</button>)}</div>
      <div className="catalogue-tabs">{selectedMeeting?.sessions.map(s => {
        const job = jobs.data?.find(j => j.session_key === s.session_key)
        const ready = s.ingested || job?.events_ready
        const preparing = pending === s.session_key || job?.state === 'queued' || job?.state === 'preparing'
        return <button key={s.session_key} disabled={preparing || s.is_cancelled} className={s.session_key === sessionKey ? 'active' : ''} onClick={() => void choose(s)}>
          <span className={`catalogue-status ${ready ? 'catalogue-status--ready' : ''}`} /> {s.session_name} <small>{preparing ? `${job?.progress ?? 0}%` : ready ? 'Ready' : s.is_cancelled ? 'Cancelled' : '↓ Prepare'}</small>
        </button>
      })}</div>
      {catalogue.loading && <p className="muted">Loading calendar…</p>}
      <button className="text-button" onClick={catalogue.refresh}>Refresh availability</button>
      {sessionKey && <button className="text-button" onClick={() => void request(`/preparation/${sessionKey}`, { method: 'POST', body: '{"telemetry":true}' }).then(jobs.refresh).catch(e => setError(String(e)))}>Prepare / retry telemetry for active session</button>}
    </details>
    {(error || catalogue.error) && <p role="alert" className="control-error">{error ?? catalogue.error}</p>}
    {jobs.data?.filter(j => ['queued', 'preparing', 'failed', 'partial', 'interrupted'].includes(j.state)).map(job => <div className="job" key={job.session_key}>
      <span>Session {job.session_key} · {job.message}</span><progress value={job.progress} max={100} />
      {job.events_ready && <button onClick={() => setSession(job.session_key)}>Open timing</button>}
      {!['queued', 'preparing'].includes(job.state) && <button onClick={() => void request(`/preparation/${job.session_key}`, { method: 'POST', body: '{"telemetry":true}' }).then(jobs.refresh).catch(e => setError(String(e)))}>Retry</button>}
    </div>)}
  </section>
}
