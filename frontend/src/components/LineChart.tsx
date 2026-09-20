export interface Series { label: string; color: string; points: { x: number; y: number }[] }
export function LineChart({ series, label, unit = 's' }: { series: Series[]; label: string; unit?: string }) {
  const points = series.flatMap(s => s.points).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))
  if (!points.length) return <p className="empty-state">No comparable samples available.</p>
  const minX = Math.min(...points.map(p => p.x)), maxX = Math.max(...points.map(p => p.x))
  const minY = Math.min(...points.map(p => p.y)), maxY = Math.max(...points.map(p => p.y))
  const x = (v: number) => 60 + (v - minX) / Math.max(maxX - minX, 1) * 800
  const y = (v: number) => 230 - (v - minY) / Math.max(maxY - minY, 0.1) * 195
  return <figure className="chart"><figcaption>{label}</figcaption><svg viewBox="0 0 900 270" role="img" aria-label={label}>
    {[0, 1, 2, 3, 4].map(i => <g key={i}><line x1="60" x2="860" y1={35 + i * 48.75} y2={35 + i * 48.75} stroke="#252b36" /><text x="4" y={40 + i * 48.75}>{(maxY - (maxY - minY) * i / 4).toFixed(1)}{unit}</text></g>)}
    {series.map(s => <polyline key={s.label} fill="none" stroke={s.color} strokeWidth="2.5" points={s.points.map(p => `${x(p.x)},${y(p.y)}`).join(' ')} />)}
    <text x="60" y="257">{minX.toFixed(0)}</text><text x="830" y="257">{maxX.toFixed(0)}</text>
  </svg><div className="chart-legend">{series.map(s => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div></figure>
}
