import { useEffect, useRef, useState } from 'react'
import { DriverTelemetry } from '../components/DriverTelemetry'
import { Header } from '../components/Header'
import { RaceBoard } from '../components/RaceBoard'
import { RaceInfo } from '../components/RaceInfo'
import { RaceStatus } from '../components/RaceStatus'
import { ReplayControls } from '../components/ReplayControls'
import { TelemetrySync } from '../components/TelemetrySync'
import { TrackMap } from '../components/TrackMap'
import { RaceBrowser } from '../components/RaceBrowser'
import { AnalysisWorkspace } from '../components/AnalysisWorkspace'
import { StrategyWorkspace } from '../components/StrategyWorkspace'
import { F1Glossary } from '../components/F1Glossary'
import { RaceWebSocket } from '../lib/websocket'
import { request } from '../lib/api'
import { useResource } from '../hooks/useResource'
import { useRaceStore } from '../stores/raceStore'
import type { Analysis } from '../types/analysis'
import type { SessionListResponse } from '../types/sessions'

export default function App() {
  const sessionKey = useRaceStore(s => s.sessionKey)
  const connected = useRaceStore(s => s.connected)
  const [view, setView] = useState('Replay')
  const [bookmarkError, setBookmarkError] = useState('')
  const linked = useRef(false)
  const sessions = useResource<SessionListResponse>('/sessions', 60_000)
  const selectedSession = sessions.data?.sessions.find(session => session.session_key === sessionKey)
  const telemetryAvailable = !sessions.loading && (selectedSession?.telemetry_available ?? true)
  const analysis = useResource<Analysis>(sessionKey && telemetryAvailable ? `/analysis/${sessionKey}` : null)
  useEffect(() => {
    if (sessionKey === null || !telemetryAvailable) return
    const socket = new RaceWebSocket(sessionKey)
    socket.connect()
    const timer = window.setInterval(() => socket.ping(), 20000)
    return () => { window.clearInterval(timer); socket.disconnect() }
  }, [sessionKey, telemetryAvailable])
  useEffect(() => {
    if (!connected || !sessionKey || linked.current) return
    const query = new URLSearchParams(window.location.search)
    if (Number(query.get('session')) !== sessionKey) return
    linked.current = true
    const time = query.get('time'), driver = query.get('driver')
    if (driver) useRaceStore.getState().setSelectedDriver(driver)
    if (time && Number.isFinite(Date.parse(time))) {
      request(`/replay/${sessionKey}/seek/time`, { method: 'POST', body: JSON.stringify({ timestamp: time }) }).catch(e => setBookmarkError(String(e)))
    }
  }, [connected, sessionKey])
  const workspaceReady = sessionKey !== null && !sessions.loading && telemetryAvailable
  const welcome = <section className="panel welcome-panel"><span className="eyebrow">{sessionKey === null ? 'YOUR ENGINEERING STATION' : 'SESSION ARCHIVE'}</span><h1>Every lap tells a story.</h1><p>{sessionKey === null ? 'Choose a fully prepared Grand Prix session to explore timing, telemetry and alternative strategies.' : 'This session will unlock automatically when its telemetry and circuit map are ready. You can explore another prepared session from the directory while Pitwall waits.'}</p></section>
  return <main className="app-shell"><Header archivePending={sessionKey !== null && !workspaceReady} /><RaceBrowser />
    {!workspaceReady ? <>
      {sessionKey !== null && <section className="archive-notice" role="status">
        <div><strong>{sessions.loading ? 'Checking session availability…' : 'Telemetry is still being processed'}</strong><span>{sessions.loading ? 'Pitwall is checking the cloud archive.' : `${selectedSession?.label ?? `Session ${sessionKey}`} will become available when telemetry and circuit coordinates are published. Pitwall checks automatically.`}</span></div>
        {!sessions.loading && <button className="text-button" onClick={sessions.refresh}>Check availability</button>}
      </section>}
      {welcome}
    </> : <>
      <nav className="workspace-nav" aria-label="Workspaces">{['Replay', 'Analyze', 'Strategy'].map((name, index) => <button key={name} className={view === name ? 'active' : ''} aria-current={view === name ? 'page' : undefined} onClick={() => setView(name)}><small>0{index + 1}</small>{name}</button>)}<span className="nav-caption">THE RACE. EVERY DETAIL.</span></nav>
      <F1Glossary />
      {bookmarkError && <p role="alert" className="control-error">{bookmarkError}</p>}
      <TelemetrySync />
      <div className="session-data-actions"><span>{view.toUpperCase()} · {analysis.data ? `${analysis.data.session.year} ${analysis.data.session.country_name} · ${analysis.data.session.session_name}` : `Session ${sessionKey}`}</span><button className="text-button" onClick={analysis.refresh}>Refresh session analysis</button></div>
      <RaceStatus /><ReplayControls key={`replay-${sessionKey}`} analysis={analysis.data} />
      {view === 'Replay' ? <><div className="dashboard-grid"><RaceBoard /><TrackMap key={`track-${sessionKey}`} /></div><DriverTelemetry /><RaceInfo /></> : analysis.data ? view === 'Analyze' ? <AnalysisWorkspace key={`analysis-${sessionKey}`} analysis={analysis.data} /> : <StrategyWorkspace key={`strategy-${sessionKey}`} analysis={analysis.data} /> : <section className="panel empty-state">{analysis.error ?? 'Loading session analysis…'}{analysis.error && <button onClick={analysis.refresh}>Retry</button>}</section>}
    </>}
    <footer className="app-footer"><span>PITWALL / INDEPENDENT RACE ANALYSIS</span><span>Timing · OpenF1 &nbsp; Telemetry · FastF1</span></footer>
  </main>
}
