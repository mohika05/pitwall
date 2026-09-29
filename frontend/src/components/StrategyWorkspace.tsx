import { useEffect, useState } from 'react'
import { getCatalogYears, getYearCatalogue, pauseReplay, request } from '../lib/api'
import { useResource } from '../hooks/useResource'
import { useRaceStore } from '../stores/raceStore'
import type { Analysis, PaceModel, Scenario } from '../types/analysis'
import type { SessionListResponse } from '../types/sessions'
import { LineChart } from './LineChart'
import { F1Term } from './F1Glossary'

function strategyError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  if (/mixed-weather|wet\/intermediate pace/i.test(message)) return 'This race included wet or changing conditions. Replay and analysis are still available, but strategy simulation currently supports dry races only.'
  if (/three clean completed laps/i.test(message)) return 'Move the replay forward until this driver has completed at least three clean racing laps, then try again.'
  if (/pit lap and simulation horizon/i.test(message)) return 'Choose a pit lap and comparison end lap after the driver’s currently completed lap.'
  if (/baseline stop must follow/i.test(message)) return 'The comparison strategy must pit after the current replay lap.'
  if (/selected compound is not/i.test(message)) return 'The tyre you want to fit must also be checked under “Tyres available for this scenario”.'
  if (/retired|non-starting|disqualified/i.test(message)) return 'A new strategy cannot be simulated after this driver retired, did not start or was disqualified. Move the replay to an earlier point or choose another driver.'
  if (/recorded lap .* missing/i.test(message)) return 'Recorded data does not cover the entire comparison. Choose an earlier end lap and try again.'
  return message || 'The strategy could not be simulated. Check the inputs and try again.'
}

function uniqueModels(items: PaceModel[] | undefined) {
  const unique = new Map<string, PaceModel>()
  for (const model of items ?? []) {
    const key = `${[...model.training_sessions].sort((a, b) => a - b).join(',')}|${model.holdout_session}|${model.version}`
    const previous = unique.get(key)
    if (!previous || model.mae_seconds < previous.mae_seconds) unique.set(key, model)
  }
  return [...unique.values()].sort((a, b) => a.mae_seconds - b.mae_seconds)
}

let catalogLabelRequest: Promise<Record<number, string>> | undefined
function loadCatalogLabels() {
  catalogLabelRequest ??= getCatalogYears().then(async ({ years }) => {
    const catalogues = await Promise.allSettled(years.map(year => getYearCatalogue(year)))
    const labels: Record<number, string> = {}
    for (const result of catalogues) {
      if (result.status !== 'fulfilled') continue
      for (const meeting of result.value.meetings) {
        const race = meeting.meeting_name?.replace(' Grand Prix', '') ?? meeting.country_name ?? meeting.location ?? 'Grand Prix'
        for (const item of meeting.sessions) labels[item.session_key] = `${result.value.year} · ${race} · ${item.session_name ?? item.session_type ?? 'Session'}`
      }
    }
    return labels
  })
  return catalogLabelRequest
}

export function StrategyWorkspace({ analysis }: { analysis: Analysis }) {
  const { state, selectedDriver } = useRaceStore()
  const driver = analysis.drivers.find(d => d.name_acronym === selectedDriver)
  const session = analysis.session.session_key
  const maxLap = Math.max(1, ...analysis.laps.filter(l => l.driver === selectedDriver).map(l => l.lap))
  const completedLap = state?.drivers[driver?.driver_number ?? 0]?.current_lap ?? 0
  const [result, setResult] = useState<Scenario | null>(null)
  const [comparison, setComparison] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [backtest, setBacktest] = useState<{ mae_seconds: number; baseline_mae_seconds: number; improvement_seconds: number; beats_baseline: boolean; bias_seconds: number; cases: { driver: string; pit_lap: number; horizon_laps: number; error_seconds: number; baseline_error_seconds: number }[]; note: string } | null>(null)
  const [trainingSessions, setTrainingSessions] = useState<number[]>([])
  const [sessionChoice, setSessionChoice] = useState('')
  const saved = useResource<Scenario[]>(`/strategy/scenarios?session_key=${session}`)
  const models = useResource<PaceModel[]>('/strategy/models')
  const sessions = useResource<SessionListResponse>('/sessions')
  const [catalogLabels, setCatalogLabels] = useState<Record<number, string>>({})
  const [mode, setMode] = useState('historical')
  useEffect(() => {
    let stopped = false
    loadCatalogLabels().then(labels => { if (!stopped) setCatalogLabels(labels) }).catch(() => undefined)
    return () => { stopped = true }
  }, [])
  if (!/race|sprint/i.test(analysis.session.session_name) || /qualifying|shootout/i.test(analysis.session.session_name)) return <section className="panel empty-state">Pit strategy is available for Race and Sprint. Use Analyze for qualifying progression and practice long runs.</section>
  async function run(form: HTMLFormElement) {
    if (!driver || !state) return
    const values = new FormData(form)
    const numeric = ['pit_lap', 'total_laps', 'pit_lane_loss', 'stationary_time', 'degradation', 'fuel_gain', 'traffic_penalty', 'warmup_loss', 'uncertainty', 'safety_car_multiplier']
    const body: Record<string, unknown> = Object.fromEntries(values)
    for (const key of numeric) body[key] = Number(values.get(key))
    body.baseline_pit_lap = values.get('baseline_pit_lap') ? Number(values.get('baseline_pit_lap')) : null
    body.available_compounds = values.getAll('available_compounds').map(String)
    body.enforce_dry_compounds = values.get('enforce_dry_compounds') === 'on'
    body.model_id = values.get('model_id') || null
    setBusy(true); setError('')
    try {
      const cursor = await pauseReplay(session)
      const response = await request<Scenario>('/strategy/simulate', { method: 'POST', body: JSON.stringify({ ...body, session_key: session, driver_number: driver.driver_number, timestamp: cursor.replay_timestamp }) })
      setResult(response); saved.refresh()
    } catch (e) { setError(strategyError(e)) } finally { setBusy(false) }
  }
  const sessionName = (key: number) => sessions.data?.sessions.find(item => item.session_key === key)?.label ?? catalogLabels[key] ?? 'Historical race'
  const eligibleTrainingSessions = sessions.data?.sessions.filter(item => item.telemetry_available && /race|sprint/i.test(item.session_name ?? '')) ?? []
  function addTrainingSession() {
    const key = Number(sessionChoice)
    if (key && !trainingSessions.includes(key)) setTrainingSessions(current => [...current, key])
    setSessionChoice('')
  }
  function trainModel() {
    setBusy(true); setError('')
    request('/strategy/models', { method: 'POST', body: JSON.stringify({ session_keys: trainingSessions }) })
      .then(() => models.refresh()).catch(e => setError(strategyError(e))).finally(() => setBusy(false))
  }
  const visibleModels = uniqueModels(models.data)
  const acceptedModels = visibleModels.filter(model => model.version >= 2 && model.accepted)
  const other = saved.data?.find(s => s.id === comparison)
  return <div className="workspace-stack">
    <div className="workspace-heading"><div><span className="eyebrow">STRATEGY LAB · {selectedDriver}</span><h2>Change the call.</h2></div><span className="muted">Branch from replay · completed lap {completedLap}</span></div>
    <aside className="scope-notice" aria-label="Strategy simulator scope"><strong>Experimental dry-race model</strong><span>Supports Soft, Medium and Hard tyres using recorded dry running. Wet and mixed-weather strategy is not calibrated, so those scenarios are unavailable.</span></aside>
    <section className="strategy-guide" aria-label="How the strategy simulator works">
      <div><b>1</b><span><strong>Choose the decision moment</strong>Use the replay controls above to stop after at least three clean laps. The simulator learns the selected driver's recent pace and current race position.</span></div>
      <div><b>2</b><span><strong>Make a different call</strong>Choose when to pit, which tyre to fit and how far ahead to simulate. Advanced controls let you test different assumptions.</span></div>
      <div><b>3</b><span><strong>Compare the outcome</strong>A negative finish delta means your plan was estimated faster. The range shows how sensitive that answer is to the assumptions.</span></div>
    </section>
    <p className="data-note">Running a scenario pauses the historical replay. Results are lap-level estimates rather than predictions of an exact finishing position.</p>
    <div className="strategy-grid"><form key={`${session}-${selectedDriver}-${completedLap}`} className="panel strategy-form" onSubmit={e => { e.preventDefault(); void run(e.currentTarget) }}>
      <div className="panel-title">Alternative strategy</div><div className="form-grid">
      <label>Give this plan a name<input name="name" defaultValue="Earlier stop" required maxLength={100} /><small>For example: “Early undercut on Hard tyres”.</small></label>
      <label>What should this plan be compared with?<select name="mode" value={mode} onChange={e => setMode(e.target.value)}><option value="historical">What actually happened in the race</option><option value="forecast">Another strategy I choose</option></select><small>{mode === 'historical' ? 'Uses the recorded laps after this replay moment.' : 'Compares two plans using only information available now.'}</small></label>
      <label>When should the driver pit?<input name="pit_lap" aria-label="Pit lap" type="number" min={completedLap + 1} max={150} defaultValue={Math.min(maxLap, completedLap + 3)} required /><small>Enter a lap after the currently completed lap.</small></label>
      <label>Which tyre should be fitted?<select name="compound" defaultValue="HARD"><option value="SOFT">Soft · fastest, shorter life</option><option value="MEDIUM">Medium · balanced pace and life</option><option value="HARD">Hard · slower, longer life</option></select></label>
      <label>How far should the comparison run?<input name="total_laps" aria-label="Simulate through lap" type="number" min={completedLap + 1} max={150} defaultValue={maxLap} required /><small>Usually the final race lap, or a shorter decision horizon.</small></label>
      <label>How should tyre pace be estimated?<select name="model_id"><option value="">Transparent formula · recommended default</option>{acceptedModels.map(m => <option key={m.id} value={m.id}>Validated ML · {m.training_sessions.length} training race{m.training_sessions.length === 1 ? '' : 's'} · tested on {sessionName(m.holdout_session)} · {m.mae_seconds.toFixed(2)}s error</option>)}</select><small>The ML option only appears after it beats the simple baseline on an unseen race. Repeated runs using the same races are shown once.</small></label>
      {mode === 'forecast' && <><label>When would the other plan pit?<input name="baseline_pit_lap" type="number" min={completedLap + 1} max={150} required /></label><label>Which tyre would the other plan use?<select name="baseline_compound"><option>HARD</option><option>MEDIUM</option><option>SOFT</option></select></label></>}
      </div><details className="assumptions"><summary>Model assumptions & tyre allocation</summary><div className="form-grid">
      {[
        ['pit_lane_loss', 'Pit-lane travel time', 'seconds', 'Time lost entering, travelling through and leaving the pit lane.', 20, 0, 90], ['stationary_time', 'Tyre-change time', 'seconds', 'Time stationary in the pit box.', 2.5, 0, 60],
        ['degradation', 'Tyre wear per lap', 'seconds', 'Estimated pace lost for every lap of tyre age.', 0.06, 0, 2], ['fuel_gain', 'Fuel-burn pace gain', 'seconds', 'Estimated pace gained each lap as fuel burns off.', 0.03, 0, 0.2],
        ['traffic_penalty', 'Traffic cost per lap', 'seconds', 'Estimated time lost when rejoining close behind another car.', 0.35, 0, 5], ['warmup_loss', 'New-tyre warm-up cost', 'seconds', 'Extra time on the first lap after a stop.', 1, 0, 10],
        ['safety_car_multiplier', 'Safety-car pit-cost multiplier', '0–1', 'How much of the normal pit-lane loss applies under neutralisation.', 0.6, 0.01, 1], ['uncertainty', 'Assumption variation', '0–1', 'Fraction used to create the optimistic and pessimistic result range.', 0.15, 0, 1],
      ].map(([name, label, unit, help, value, min, max]) => <label key={String(name)}>{label} ({unit})<input name={String(name)} type="number" step="0.01" defaultValue={value} min={min} max={max} required /><small>{help}</small></label>)}
      <fieldset className="compound-options"><legend>Tyres available for this scenario</legend>{['SOFT', 'MEDIUM', 'HARD'].map(compound => <label className="check-label" key={compound}><input name="available_compounds" value={compound} type="checkbox" defaultChecked />{compound[0] + compound.slice(1).toLowerCase()}</label>)}</fieldset>
      <label className="check-label"><input name="enforce_dry_compounds" type="checkbox" defaultChecked />Apply the race rule requiring two different dry compounds</label>
      </div></details><button className="primary-button" disabled={busy || !state}>{busy ? 'Simulating…' : 'Branch & simulate →'}</button>
      {error && <div role="alert" className="strategy-error"><strong>Couldn’t run this strategy</strong><span>{error}</span></div>}
    </form>
    <section className="panel"><div className="panel-title">Saved scenarios</div><div className="scenario-list">{saved.loading ? <p className="empty-state">Loading saved scenarios…</p> : saved.error ? <div className="resource-error" role="alert"><p>{saved.error}</p><button onClick={saved.refresh}>Retry</button></div> : saved.data?.length ? saved.data.map(s => <button key={s.id} onClick={() => setResult(s)}><span>{s.assumptions.name}<small>Lap {s.assumptions.pit_lap} · {s.assumptions.compound} · {s.assumptions.mode}</small></span><strong className={s.delta_seconds < 0 ? 'positive' : ''}>{s.delta_seconds > 0 ? '+' : ''}{s.delta_seconds.toFixed(2)}s</strong></button>) : <p className="empty-state">Your experiments will appear here.</p>}</div></section></div>
    {result && <section className="panel"><div className="panel-title">{result.assumptions.name} · {result.comparison}</div><div className="result-summary"><div><span className="eyebrow">ESTIMATED FINISH <F1Term term="Delta">DELTA</F1Term></span><strong className={result.delta_seconds < 0 ? 'positive' : ''}>{result.delta_seconds > 0 ? '+' : ''}{result.delta_seconds.toFixed(2)}s</strong><small>Negative means faster than baseline</small></div><div><span className="eyebrow">ASSUMPTION RANGE</span><strong>{result.sensitivity.optimistic.toFixed(1)} to {result.sensitivity.pessimistic.toFixed(1)}s</strong><small>{result.uncertainty_note}</small></div></div>
      <label className="panel-note">Overlay saved scenario <select value={comparison} onChange={e => setComparison(e.target.value)}><option value="">None</option>{saved.data?.filter(s => s.id !== result.id && s.branch_lap === result.branch_lap).map(s => <option value={s.id} key={s.id}>{s.assumptions.name}</option>)}</select></label>
      <LineChart label="Cumulative delta to baseline · lap number" series={[{ label: result.assumptions.name, color: '#e10600', points: result.trajectory.map(p => ({ x: p.lap, y: p.delta })) }, ...(other ? [{ label: other.assumptions.name, color: '#64d5b3', points: other.trajectory.map(p => ({ x: p.lap, y: p.delta })) }] : [])]} />
      <div className="table-scroll"><table><thead><tr><th>Stop lap</th><th>Compound</th><th>Estimated rejoin</th><th>Delta</th></tr></thead><tbody>{result.trajectory.filter(p => p.pit).map(p => <tr key={p.lap}><td>{p.lap}</td><td>{p.compound}</td><td>{p.rejoin_position ? `P${p.rejoin_position}` : 'Unavailable'}</td><td>{p.delta.toFixed(2)}s</td></tr>)}</tbody></table></div>
      <ul className="model-notes">{result.warnings.map(w => <li key={w}>{w}</li>)}</ul>
    </section>}
    <section className="panel model-panel"><div className="panel-title">Validate against recorded pit decisions</div><p className="panel-note">Follow each driver's recorded first supported stop through a dry, non-neutralized horizon and compare predicted elapsed time with observed laps and a constant-pace baseline.</p><button className="validation-button" disabled={busy} onClick={() => { setBusy(true); setError(''); request<NonNullable<typeof backtest>>(`/strategy/backtest/${session}`, { method: 'POST' }).then(setBacktest).catch(e => setError(strategyError(e))).finally(() => setBusy(false)) }}>Run race backtest</button>{backtest && <><p className="panel-note"><F1Term term="MAE">Model MAE</F1Term> {backtest.mae_seconds.toFixed(2)}s · Baseline MAE {backtest.baseline_mae_seconds.toFixed(2)}s · <F1Term term="Bias">Bias</F1Term> {backtest.bias_seconds.toFixed(2)}s · {backtest.beats_baseline ? `Model improves by ${backtest.improvement_seconds.toFixed(2)}s` : 'Baseline performs better'} · {backtest.note}</p><div className="table-scroll"><table><thead><tr><th>Driver</th><th>Recorded pit lap</th><th>Horizon</th><th>Model error</th><th>Baseline error</th></tr></thead><tbody>{backtest.cases.map(c => <tr key={c.driver}><td>{c.driver}</td><td>{c.pit_lap}</td><td>{c.horizon_laps} laps</td><td>{c.error_seconds.toFixed(2)}s</td><td>{c.baseline_error_seconds.toFixed(2)}s</td></tr>)}</tbody></table></div></>}</section>
    <details className="panel model-panel model-lab" open><summary><span><span className="eyebrow">OPTIONAL MODEL LAB</span>Choose races to train and test the ML model</span><small>Named historical sessions</small></summary><p className="panel-note">Choose at least two historical races with telemetry. The model learns tyre-wear patterns from the earlier races and reserves the newest selected race as a <F1Term term="Holdout">holdout</F1Term> test. It becomes selectable above only if its average error is at least 5% lower than the simple baseline.</p>
      <div className="session-picker"><label>Add a historical race<select aria-label="Historical race" value={sessionChoice} onChange={e => setSessionChoice(e.target.value)}><option value="">Choose a race…</option>{eligibleTrainingSessions.filter(item => !trainingSessions.includes(item.session_key)).map(item => <option key={item.session_key} value={item.session_key}>{item.label}</option>)}</select></label><button type="button" disabled={!sessionChoice} onClick={addTrainingSession}>Add race</button></div>
      {sessions.loading && <p className="panel-note">Loading historical races…</p>}{sessions.error && <div className="resource-error" role="alert"><p>{sessions.error}</p><button onClick={sessions.refresh}>Retry</button></div>}
      <ol className="selected-sessions">{trainingSessions.map((key, index) => <li key={key}><span><strong>{sessionName(key)}</strong><small>{index === trainingSessions.length - 1 && trainingSessions.length > 1 ? 'Holdout test race' : 'Training race'}</small></span><button type="button" aria-label={`Remove ${sessionName(key)}`} onClick={() => setTrainingSessions(current => current.filter(item => item !== key))}>Remove</button></li>)}</ol>
      <div className="model-action"><button type="button" disabled={busy || trainingSessions.length < 2} onClick={trainModel}>{busy ? 'Training and testing…' : 'Train & test model'}</button>{trainingSessions.length < 2 && <small>Select at least two races.</small>}</div>
      {models.loading ? <p className="empty-state">Loading validated models…</p> : models.error ? <div className="resource-error" role="alert"><p>{models.error}</p><button onClick={models.refresh}>Retry</button></div> : <div className="table-scroll"><table><thead><tr><th>Training data</th><th><F1Term term="Holdout">Test race</F1Term></th><th>Model <F1Term term="MAE">error</F1Term></th><th>Simple baseline</th><th>Result</th></tr></thead><tbody>{visibleModels.map(m => <tr key={m.id}><td><span title={m.training_sessions.map(sessionName).join('\n')}>{m.training_sessions.length} historical race{m.training_sessions.length === 1 ? '' : 's'}</span></td><td>{sessionName(m.holdout_session)}</td><td>{m.mae_seconds.toFixed(3)}s</td><td>{m.baseline_mae_seconds.toFixed(3)}s</td><td>{m.version >= 2 && m.accepted ? 'Passed · available to use' : 'Did not beat baseline'}</td></tr>)}</tbody></table>{!visibleModels.length && <p className="empty-state">No validated pace models are available. The transparent formula remains available.</p>}</div>}</details>
  </div>
}
