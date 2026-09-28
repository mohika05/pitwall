import { useState } from 'react'
import type { Analysis, Lap } from '../types/analysis'
import { useRaceStore } from '../stores/raceStore'
import { useResource } from '../hooks/useResource'
import { request } from '../lib/api'
import { LineChart } from './LineChart'
import { F1Term } from './F1Glossary'

const time = (value: number | null | undefined) => value == null ? '—' : `${Math.floor(value / 60)}:${(value % 60).toFixed(3).padStart(6, '0')}`
interface WindowData { car: { Date: string; Speed: number; Throttle: number; Brake: boolean; RPM: number; nGear: number }[] }

function TelemetryComparison({ session, first, second }: { session: number; first?: Lap; second?: Lap }) {
  const [metric, setMetric] = useState<'Speed' | 'Throttle' | 'RPM' | 'nGear'>('Speed')
  const path = (lap?: Lap) => lap ? `/telemetry/${session}/drivers/${lap.driver}/window?${new URLSearchParams({ start: lap.start, end: lap.end, max_points: '500' })}` : null
  const one = useResource<WindowData>(path(first)), two = useResource<WindowData>(path(second))
  return <section className="panel"><div className="panel-title">Telemetry comparison <select aria-label="Telemetry metric" value={metric} onChange={e => setMetric(e.target.value as typeof metric)}>{['Speed', 'Throttle', 'RPM', 'nGear'].map(m => <option key={m}>{m}</option>)}</select></div>
    <p className="panel-note">Aligned by elapsed lap time (seconds). Differences in lap length remain visible.</p>
    {one.error || two.error ? <p className="control-error">{one.error ?? two.error}</p> : one.loading || two.loading ? <p className="empty-state">Loading telemetry…</p> : <LineChart label={`${metric} overlay`} unit={metric === 'Speed' ? 'km/h' : metric === 'Throttle' ? '%' : ''} series={[[one.data, first, '#e8edf5'], [two.data, second, '#e10600']].map(([data, lap, color]) => {
      const rows = data as WindowData | undefined, selected = lap as Lap | undefined
      return { label: selected ? `${selected.driver} · lap ${selected.lap}` : 'Select lap', color: color as string, points: rows?.car.filter(r => r[metric] != null).map(r => ({ x: (Date.parse(r.Date) - Date.parse(selected!.start)) / 1000, y: r[metric] })) ?? [] }
    })} />}
  </section>
}

export function AnalysisWorkspace({ analysis }: { analysis: Analysis }) {
  const selected = useRaceStore(s => s.selectedDriver)
  const [compare, setCompare] = useState('')
  const [stage, setStage] = useState('All')
  const [lapOne, setLapOne] = useState<number | null>(null)
  const [lapTwo, setLapTwo] = useState<number | null>(null)
  const [error, setError] = useState('')
  const second = compare || analysis.drivers.find(d => d.name_acronym !== selected)?.name_acronym || selected
  const visibleLaps = stage === 'All' ? analysis.laps : analysis.laps.filter(l => l.stage === stage)
  const firstLaps = visibleLaps.filter(l => l.driver === selected)
  const secondLaps = visibleLaps.filter(l => l.driver === second)
  const firstLap = firstLaps.find(l => l.lap === lapOne) ?? firstLaps[0]
  const secondLap = secondLaps.find(l => l.lap === lapTwo) ?? secondLaps[0]
  const qualifying = /qualifying|shootout/i.test(analysis.session.session_name)
  const practice = /practice/i.test(analysis.session.session_name)
  async function jump(timestamp: string) {
    try { await request(`/replay/${analysis.session.session_key}/seek/time`, { method: 'POST', body: JSON.stringify({ timestamp }) }); setError('') }
    catch (e) { setError(String(e)) }
  }
  return <div className="workspace-stack">
    <div className="workspace-heading"><div><span className="eyebrow">{qualifying ? 'QUALIFYING' : practice ? 'LONG RUNS' : 'RACE ANALYSIS'}</span><h2>Find the difference.</h2></div><label>Compare {selected} with <select value={second} onChange={e => setCompare(e.target.value)}>{analysis.drivers.map(d => <option key={d.driver_number}>{d.name_acronym}</option>)}</select></label></div>
    {qualifying && <label className="comparison-selectors">Qualifying stage <select aria-label="Qualifying stage" value={stage} onChange={e => setStage(e.target.value)}>{['All', 'Q1', 'Q2', 'Q3'].map(value => <option key={value}>{value}</option>)}</select></label>}
    {qualifying && <section className="panel"><div className="panel-title">Qualifying progression · official stage times</div><div className="table-scroll"><table><thead><tr><th>Driver</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Result</th></tr></thead><tbody>{analysis.qualifying.map(q => <tr key={q.driver_number}><td>{analysis.drivers.find(d => d.driver_number === q.driver_number)?.name_acronym}</td><td>{time(q.Q1)}</td><td>{time(q.Q2)}</td><td>{time(q.Q3)}</td><td>{q.Q3 != null ? 'Q3 time recorded' : q.Q2 != null ? 'No Q3 time' : 'No Q2/Q3 time'} · P{q.position ?? '—'}</td></tr>)}</tbody></table></div>{!analysis.qualifying.length && <p className="empty-state">Prepare FastF1 telemetry to load recorded qualifying stages. Elimination is not inferred from race positions.</p>}</section>}
    <section className="panel"><LineChart label="Lap times · lap number" series={[{ label: selected, color: '#e8edf5', points: firstLaps.map(l => ({ x: l.lap, y: l.seconds })) }, { label: second, color: '#e10600', points: secondLaps.map(l => ({ x: l.lap, y: l.seconds })) }]} /></section>
    <section className="panel"><div className="panel-title"><F1Term term="Stint">Stint history</F1Term></div><div className="stint-list">{[selected, second].map(driver => <div className="stint-row" key={driver}><strong>{driver}</strong>{analysis.stints.filter(s => s.driver === driver).map(s => <span key={s.stint_number} className={`stint tyre-${s.compound}`} style={{ flexGrow: Math.max(1, (s.lap_end ?? s.lap_start) - s.lap_start + 1) }}>{s.compound} <small>L{s.lap_start}–{s.lap_end ?? '?'}</small></span>)}</div>)}</div></section>
    <div className="comparison-selectors"><label>{selected} lap <select value={firstLap?.lap ?? ''} onChange={e => setLapOne(Number(e.target.value))}>{firstLaps.map(l => <option key={l.lap} value={l.lap}>{l.lap} · {time(l.seconds)}</option>)}</select></label><label>{second} lap <select value={secondLap?.lap ?? ''} onChange={e => setLapTwo(Number(e.target.value))}>{secondLaps.map(l => <option key={l.lap} value={l.lap}>{l.lap} · {time(l.seconds)}</option>)}</select></label></div>
    <TelemetryComparison session={analysis.session.session_key} first={firstLap} second={secondLap} />
    <div className="analysis-grid"><section className="panel"><div className="panel-title">{practice ? <>Long-run pace · clean-lap <F1Term term="Median pace">median</F1Term></> : 'Driver pace summary'}</div><div className="table-scroll pace-table"><table><thead><tr><th>Driver</th><th>Laps</th><th>Best</th><th><F1Term term="Median pace">Median</F1Term></th></tr></thead><tbody>{analysis.drivers.map(d => <tr key={d.driver_number}><td><button className="text-button" onClick={() => useRaceStore.getState().setSelectedDriver(d.name_acronym)}>{d.name_acronym}</button></td><td>{d.laps}</td><td>{time(d.best)}</td><td>{time(d.median_pace)}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><div className="panel-title"><F1Term term="Race control">Race-control</F1Term> & pit-stop timeline</div><div className="event-list">{analysis.timeline.map(event => <button key={event.id} onClick={() => void jump(event.timestamp)}><time>{new Date(event.timestamp).toLocaleTimeString()}</time><span>{event.driver ? `${event.driver} · ` : ''}{event.payload.message ?? `Pit stop · lap ${event.lap ?? '—'}`}</span></button>)}</div>{error && <p className="control-error">{error}</p>}</section></div>
    <section className="panel"><div className="panel-title">Official classification · separate from running order</div><div className="classification">{analysis.official_result.map(row => <span key={row.driver_number}>P{row.position ?? '—'} {analysis.drivers.find(d => d.driver_number === row.driver_number)?.name_acronym ?? row.driver_number}{row.dnf ? ' · DNF' : row.dsq ? ' · DSQ' : row.dns ? ' · DNS' : ''}</span>)}</div></section>
    <p className="data-note">{analysis.quality.source} · Telemetry {analysis.quality.telemetry_drivers.length}/{analysis.quality.total_drivers} drivers. {analysis.quality.note}</p>
  </div>
}
