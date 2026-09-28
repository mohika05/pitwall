import { useState } from 'react'
import { pauseReplay, request } from '../lib/api'
import { useResource } from '../hooks/useResource'
import { useRaceStore } from '../stores/raceStore'
import type { Analysis, PaceModel, Scenario } from '../types/analysis'
import { LineChart } from './LineChart'
import { F1Term } from './F1Glossary'

export function StrategyWorkspace({ analysis }: { analysis: Analysis }) {
  const { state, selectedDriver } = useRaceStore()
  const driver = analysis.drivers.find(d => d.name_acronym === selectedDriver)
  const session = analysis.session.session_key
  const maxLap = Math.max(1, ...analysis.laps.filter(l => l.driver === selectedDriver).map(l => l.lap))
  const [result, setResult] = useState<Scenario | null>(null)
  const [comparison, setComparison] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [backtest, setBacktest] = useState<{ mae_seconds: number; baseline_mae_seconds: number; improvement_seconds: number; beats_baseline: boolean; bias_seconds: number; cases: { driver: string; pit_lap: number; horizon_laps: number; error_seconds: number; baseline_error_seconds: number }[]; note: string } | null>(null)
  const [training, setTraining] = useState('')
  const saved = useResource<Scenario[]>(`/strategy/scenarios?session_key=${session}`)
  const models = useResource<PaceModel[]>('/strategy/models')
  const [mode, setMode] = useState('historical')
  if (!/race|sprint/i.test(analysis.session.session_name) || /qualifying|shootout/i.test(analysis.session.session_name)) return <section className="panel empty-state">Pit strategy is available for Race and Sprint. Use Analyze for qualifying progression and practice long runs.</section>
  async function run(form: HTMLFormElement) {
    if (!driver || !state) return
    const values = new FormData(form)
    const numeric = ['pit_lap', 'total_laps', 'pit_lane_loss', 'stationary_time', 'degradation', 'fuel_gain', 'traffic_penalty', 'warmup_loss', 'uncertainty', 'safety_car_multiplier']
    const body: Record<string, unknown> = Object.fromEntries(values)
    for (const key of numeric) body[key] = Number(values.get(key))
    body.baseline_pit_lap = values.get('baseline_pit_lap') ? Number(values.get('baseline_pit_lap')) : null
    body.available_compounds = String(values.get('available_compounds')).split(',').map(s => s.trim().toUpperCase())
    body.enforce_dry_compounds = values.get('enforce_dry_compounds') === 'on'
    body.model_id = values.get('model_id') || null
    setBusy(true); setError('')
    try {
      const cursor = await pauseReplay(session)
      const response = await request<Scenario>('/strategy/simulate', { method: 'POST', body: JSON.stringify({ ...body, session_key: session, driver_number: driver.driver_number, timestamp: cursor.replay_timestamp }) })
      setResult(response); saved.refresh()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  const other = saved.data?.find(s => s.id === comparison)
  return <div className="workspace-stack">
    <div className="workspace-heading"><div><span className="eyebrow">STRATEGY LAB · {selectedDriver}</span><h2>Change the call.</h2></div><span className="muted">Branch from replay · completed lap {state?.drivers[driver?.driver_number ?? 0]?.current_lap ?? 0}</span></div>
    <p className="data-note">Seek to a decision point with at least three clean completed laps. Running a scenario pauses the historical replay. Results are lap-level estimates.</p>
    <div className="strategy-grid"><form className="panel strategy-form" onSubmit={e => { e.preventDefault(); void run(e.currentTarget) }}>
      <div className="panel-title">Alternative strategy</div><div className="form-grid">
      <label>Scenario name<input name="name" defaultValue="Earlier stop" required maxLength={100} /></label>
      <label>Comparison mode<select name="mode" value={mode} onChange={e => setMode(e.target.value)}><option value="historical">Historical what-if</option><option value="forecast">Decision-time forecast</option></select></label>
      <label>Pit lap<input name="pit_lap" type="number" min={1} max={150} defaultValue={Math.min(maxLap, (state?.current_lap ?? 0) + 3)} required /></label>
      <label>Next <F1Term term="Tyre compound">compound</F1Term><select name="compound" defaultValue="HARD"><option>SOFT</option><option>MEDIUM</option><option>HARD</option></select></label>
      <label>Simulate through lap<input name="total_laps" type="number" min={1} max={150} defaultValue={maxLap} required /></label>
      <label>Pace model<select name="model_id"><option value="">Deterministic baseline</option>{models.data?.filter(m => m.version >= 2 && m.accepted).map(m => <option key={m.id} value={m.id}>ML · holdout MAE {m.mae_seconds.toFixed(2)}s</option>)}</select></label>
      {mode === 'forecast' && <><label>Baseline pit lap<input name="baseline_pit_lap" type="number" min={1} max={150} required /></label><label>Baseline compound<select name="baseline_compound"><option>HARD</option><option>MEDIUM</option><option>SOFT</option></select></label></>}
      </div><details className="assumptions"><summary>Model assumptions & tyre allocation</summary><div className="form-grid">
      {[
        ['pit_lane_loss', 'Pit transit loss (s)', 20, 0, 90], ['stationary_time', 'Stationary stop (s)', 2.5, 0, 60],
        ['degradation', 'Wear (s/lap of age)', 0.06, 0, 2], ['fuel_gain', 'Fuel pace gain (s/lap)', 0.03, 0, 0.2],
        ['traffic_penalty', 'Traffic loss (s/lap)', 0.35, 0, 5], ['warmup_loss', 'Warm-up loss (s)', 1, 0, 10],
        ['safety_car_multiplier', 'Neutralized pit transit multiplier', 0.6, 0.01, 1], ['uncertainty', 'Sensitivity fraction', 0.15, 0, 1],
      ].map(([name, label, value, min, max]) => <label key={String(name)}>{label}<input name={String(name)} type="number" step="0.01" defaultValue={value} min={min} max={max} required /></label>)}
      <label>Available compounds<input name="available_compounds" defaultValue="SOFT,MEDIUM,HARD" required /></label>
      <label className="check-label"><input name="enforce_dry_compounds" type="checkbox" />Require two dry compounds for this race</label>
      </div></details><button className="primary-button" disabled={busy || !state}>{busy ? 'Simulating…' : 'Branch & simulate →'}</button>
      {error && <p role="alert" className="control-error">{error}</p>}
    </form>
    <section className="panel"><div className="panel-title">Saved scenarios</div><div className="scenario-list">{saved.data?.map(s => <button key={s.id} onClick={() => setResult(s)}><span>{s.assumptions.name}<small>Lap {s.assumptions.pit_lap} · {s.assumptions.compound} · {s.assumptions.mode}</small></span><strong className={s.delta_seconds < 0 ? 'positive' : ''}>{s.delta_seconds > 0 ? '+' : ''}{s.delta_seconds.toFixed(2)}s</strong></button>)}{!saved.data?.length && <p className="empty-state">Your experiments will appear here.</p>}</div></section></div>
    {result && <section className="panel"><div className="panel-title">{result.assumptions.name} · {result.comparison}</div><div className="result-summary"><div><span className="eyebrow">ESTIMATED FINISH <F1Term term="Delta">DELTA</F1Term></span><strong className={result.delta_seconds < 0 ? 'positive' : ''}>{result.delta_seconds > 0 ? '+' : ''}{result.delta_seconds.toFixed(2)}s</strong><small>Negative means faster than baseline</small></div><div><span className="eyebrow">ASSUMPTION RANGE</span><strong>{result.sensitivity.optimistic.toFixed(1)} to {result.sensitivity.pessimistic.toFixed(1)}s</strong><small>{result.uncertainty_note}</small></div></div>
      <label className="panel-note">Overlay saved scenario <select value={comparison} onChange={e => setComparison(e.target.value)}><option value="">None</option>{saved.data?.filter(s => s.id !== result.id && s.branch_lap === result.branch_lap).map(s => <option value={s.id} key={s.id}>{s.assumptions.name}</option>)}</select></label>
      <LineChart label="Cumulative delta to baseline · lap number" series={[{ label: result.assumptions.name, color: '#e10600', points: result.trajectory.map(p => ({ x: p.lap, y: p.delta })) }, ...(other ? [{ label: other.assumptions.name, color: '#64d5b3', points: other.trajectory.map(p => ({ x: p.lap, y: p.delta })) }] : [])]} />
      <div className="table-scroll"><table><thead><tr><th>Stop lap</th><th>Compound</th><th>Estimated rejoin</th><th>Delta</th></tr></thead><tbody>{result.trajectory.filter(p => p.pit).map(p => <tr key={p.lap}><td>{p.lap}</td><td>{p.compound}</td><td>{p.rejoin_position ? `P${p.rejoin_position}` : 'Unavailable'}</td><td>{p.delta.toFixed(2)}s</td></tr>)}</tbody></table></div>
      <ul className="model-notes">{result.warnings.map(w => <li key={w}>{w}</li>)}</ul>
    </section>}
    <section className="panel model-panel"><div className="panel-title">Validate against recorded pit decisions</div><p className="panel-note">Follow each driver's recorded first supported stop through a dry, non-neutralized horizon and compare predicted elapsed time with observed laps and a constant-pace baseline.</p><button className="validation-button" disabled={busy} onClick={() => { setBusy(true); request<NonNullable<typeof backtest>>(`/strategy/backtest/${session}`, { method: 'POST' }).then(setBacktest).catch(e => setError(String(e))).finally(() => setBusy(false)) }}>Run race backtest</button>{backtest && <><p className="panel-note"><F1Term term="MAE">Model MAE</F1Term> {backtest.mae_seconds.toFixed(2)}s · Baseline MAE {backtest.baseline_mae_seconds.toFixed(2)}s · <F1Term term="Bias">Bias</F1Term> {backtest.bias_seconds.toFixed(2)}s · {backtest.beats_baseline ? `Model improves by ${backtest.improvement_seconds.toFixed(2)}s` : 'Baseline performs better'} · {backtest.note}</p><div className="table-scroll"><table><thead><tr><th>Driver</th><th>Recorded pit lap</th><th>Horizon</th><th>Model error</th><th>Baseline error</th></tr></thead><tbody>{backtest.cases.map(c => <tr key={c.driver}><td>{c.driver}</td><td>{c.pit_lap}</td><td>{c.horizon_laps} laps</td><td>{c.error_seconds.toFixed(2)}s</td><td>{c.baseline_error_seconds.toFixed(2)}s</td></tr>)}</tbody></table></div></>}</section>
    <section className="panel model-panel"><div className="panel-title">Pace model training & validation</div><p className="panel-note">Enter at least two prepared session IDs. The latest session is <F1Term term="Holdout">held out</F1Term>; only version 2 models that beat the baseline by at least 5% are eligible. A model cannot be used on its training or validation sessions.</p><form onSubmit={e => { e.preventDefault(); setBusy(true); request('/strategy/models', { method: 'POST', body: JSON.stringify({ session_keys: training.split(',').map(Number) }) }).then(models.refresh).catch(e => setError(String(e))).finally(() => setBusy(false)) }}><label>Session IDs<input placeholder="9896, 9900" value={training} onChange={e => setTraining(e.target.value)} required /></label><button disabled={busy}>Train & evaluate</button></form><div className="table-scroll"><table><thead><tr><th>Training sessions</th><th><F1Term term="Holdout">Holdout</F1Term></th><th>Model <F1Term term="MAE">MAE</F1Term></th><th>Baseline <F1Term term="MAE">MAE</F1Term></th><th>Status</th></tr></thead><tbody>{models.data?.map(m => <tr key={m.id}><td>{m.training_sessions.join(', ')}</td><td>{m.holdout_session}</td><td>{m.mae_seconds.toFixed(3)}s</td><td>{m.baseline_mae_seconds.toFixed(3)}s</td><td>{m.version >= 2 && m.accepted ? 'Eligible' : 'Fallback retained'}</td></tr>)}</tbody></table></div></section>
  </div>
}
