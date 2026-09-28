import { useEffect, useState } from 'react'
import { getCatalogYears, getSessions } from '../lib/api'
import { useRaceStore } from '../stores/raceStore'
import { useResource } from '../hooks/useResource'
import type { YearCatalogue } from '../types/catalog'

export function RaceBrowser() {
  const sessionKey = useRaceStore(s => s.sessionKey)
  const setSession = useRaceStore(s => s.setSessionKey)
  const [years, setYears] = useState<number[]>([])
  const [year, setYear] = useState<number | null>(null)
  const [meeting, setMeeting] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const catalogue = useResource<YearCatalogue>(year ? `/catalog/${year}` : null)
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
  const seasonSessions = meetings.flatMap(m => m.sessions).filter(s => !s.is_cancelled)
  const readySessions = seasonSessions.filter(s => s.telemetry_available).length
  return <section className="race-browser">
    <div className="race-browser-header">
      <div><span className="eyebrow">SESSION DIRECTORY</span><h2>{selectedMeeting?.meeting_name ?? 'Choose your Grand Prix'}</h2></div>
      <div className="race-browser-meta">
        {!catalogue.loading && seasonSessions.length > 0 && <span>{readySessions} of {seasonSessions.length} sessions ready</span>}
        <label className="season-control">Season <select aria-label="Season" value={year ?? ''} onChange={e => { setYear(Number(e.target.value)); setMeeting(null) }}>{years.map(y => <option key={y}>{y}</option>)}</select></label>
      </div>
    </div>
    <details open={!sessionKey}>
      <summary>{selected?.session_name ?? 'Browse races and sessions'} <span className="muted">· Change session</span></summary>
      <div className="catalogue-tabs" aria-label="Grand Prix weekends">{meetings.map(m => <button key={m.meeting_key} className={selectedMeeting?.meeting_key === m.meeting_key ? 'active' : ''} onClick={() => setMeeting(m.meeting_key)}>{m.meeting_name?.replace(' Grand Prix', '') ?? m.location}</button>)}</div>
      <div className="catalogue-tabs">{selectedMeeting?.sessions.map(s => {
        const ready = s.ingested
        return <button key={s.session_key} disabled={!ready || s.is_cancelled} className={s.session_key === sessionKey ? 'active' : ''} onClick={() => setSession(s.session_key)}>
          <span className={`catalogue-status ${ready ? 'catalogue-status--ready' : ''}`} /> {s.session_name} <small>{s.telemetry_available ? 'Full data' : ready ? 'Timing ready' : s.is_cancelled ? 'Cancelled' : 'Awaiting archive'}</small>
        </button>
      })}</div>
      {catalogue.loading && <p className="muted">Loading calendar…</p>}
      <button className="text-button" onClick={catalogue.refresh}>Refresh availability</button>
    </details>
    {(error || catalogue.error) && <p role="alert" className="control-error">{error ?? catalogue.error}</p>}
  </section>
}
