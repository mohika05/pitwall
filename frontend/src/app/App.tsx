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

export default function App() {
  const sessionKey = useRaceStore(s => s.sessionKey)
  const connected = useRaceStore(s => s.connected)
  const [view, setView] = useState('Replay')
  const [bookmarkError, setBookmarkError] = useState('')
  const linked = useRef(false)
  const analysis = useResource<Analysis>(sessionKey ? `/analysis/${sessionKey}` : null)
  useEffect(() => {
    if (sessionKey === null) return
    const socket = new RaceWebSocket(sessionKey)
    socket.connect()
    const timer = window.setInterval(() => socket.ping(), 20000)
    return () => { window.clearInterval(timer); socket.disconnect() }
  }, [sessionKey])
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
  return <main className="app-shell"><Header /><RaceBrowser />
    <nav className="workspace-nav" aria-label="Workspaces">{['Replay', 'Analyze', 'Strategy'].map((name, index) => <button key={name} className={view === name ? 'active' : ''} aria-current={view === name ? 'page' : undefined} onClick={() => setView(name)}><small>0{index + 1}</small>{name}</button>)}<span className="nav-caption">THE RACE. EVERY DETAIL.</span></nav>
    {bookmarkError && <p role="alert" className="control-error">{bookmarkError}</p>}
    {sessionKey !== null && <TelemetrySync />}
    {sessionKey === null ? <section className="panel welcome-panel"><span className="eyebrow">YOUR ENGINEERING STATION</span><h1>Every lap tells a story.</h1><p>Choose a Grand Prix and prepare a session to explore timing, telemetry and alternative strategies.</p></section> : <>
      <div className="session-data-actions"><span>{view.toUpperCase()} · {analysis.data ? `${analysis.data.session.year} ${analysis.data.session.country_name} · ${analysis.data.session.session_name}` : `Session ${sessionKey}`}</span><button className="text-button" onClick={analysis.refresh}>Refresh session analysis</button></div>
      <RaceStatus /><ReplayControls key={`replay-${sessionKey}`} analysis={analysis.data} />
      {view === 'Replay' ? <><div className="dashboard-grid"><RaceBoard /><TrackMap key={`track-${sessionKey}`} /></div><DriverTelemetry /><RaceInfo /></> : analysis.data ? view === 'Analyze' ? <AnalysisWorkspace key={`analysis-${sessionKey}`} analysis={analysis.data} /> : <StrategyWorkspace key={`strategy-${sessionKey}`} analysis={analysis.data} /> : <section className="panel empty-state">{analysis.error ?? 'Loading session analysis…'}{analysis.error && <button onClick={analysis.refresh}>Retry</button>}</section>}
    </>}
    <F1Glossary />
    <footer className="app-footer"><span>PITWALL / INDEPENDENT RACE ANALYSIS</span><span>Timing · OpenF1 &nbsp; Telemetry · FastF1</span></footer>
  </main>
}
