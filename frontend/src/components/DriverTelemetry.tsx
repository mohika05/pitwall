import { useRaceStore } from '../stores/raceStore'
export function DriverTelemetry() {
  const selected = useRaceStore(s => s.selectedDriver)
  const telemetry = useRaceStore(s => s.telemetry)
  const driver = telemetry?.drivers.find(d => d.driver === selected)
  const car = driver?.car
  return <section className="panel telemetry-panel"><div className="panel-title telemetry-title"><span>Driver instrumentation</span><strong>{selected || 'Select driver'}</strong></div>
    {!car ? <div className="empty-state">{driver?.error ? 'Telemetry unavailable for this driver. Prepare the session to download it.' : 'Waiting for telemetry samples…'}</div> : <div className="telemetry-grid">
      <div className="telemetry-stat telemetry-primary"><span>SPEED</span><strong>{car.Speed?.toFixed(0) ?? '—'}</strong><small>km/h</small></div>
      <div className="telemetry-stat telemetry-primary"><span>GEAR</span><strong>{car.nGear ?? '—'}</strong><small>{car.RPM?.toFixed(0) ?? '—'} RPM</small></div>
      <div className="telemetry-stat"><span>THROTTLE</span><strong>{car.Throttle?.toFixed(0) ?? '—'}%</strong><meter min={0} max={100} value={car.Throttle ?? 0} aria-label="Throttle percentage" /></div>
      <div className="telemetry-stat"><span>BRAKE</span><strong>{car.Brake == null ? '—' : car.Brake ? 'ON' : 'OFF'}</strong><meter className="brake-meter" min={0} max={1} value={car.Brake ? 1 : 0} aria-label="Brake applied" /></div>
      <div className="telemetry-stat"><span>DRS SIGNAL</span><strong>{car.DRS ?? '—'}</strong><small>Recorded provider value</small></div>
      <div className="telemetry-stat"><span>DRIVER LAP</span><strong>{car.LapNumber ?? '—'}</strong><small>{driver?.position?.Status ?? 'Position unavailable'}</small></div>
    </div>}
    {driver && <div className="telemetry-quality">Car sample offset {driver.car_sample_age_seconds?.toFixed(2) ?? '—'}s · Position offset {driver.position_sample_age_seconds?.toFixed(2) ?? '—'}s · Recorded samples</div>}
  </section>
}
