import { useId, useState, type KeyboardEvent, type ReactNode } from 'react'

const F1_TERMS = {
  'DRS': 'Drag Reduction System. A movable rear-wing flap that reduces drag and raises straight-line speed when its use is permitted.',
  'Tyre compound': 'The softness of a tyre. Soft is usually quicker but wears sooner; medium balances pace and life; hard usually lasts longest.',
  'Stint': 'A continuous run on one set of tyres, from the start or a pit exit until the next pit stop or the finish.',
  'Tyre age': 'The number of laps completed on the current set of tyres. Older tyres usually provide less grip.',
  'Gap': 'The time separating a driver from the leader or the car directly ahead.',
  'Delta': 'A time difference. A negative strategy delta means the simulated plan is faster; a positive delta means it is slower.',
  'Pit window': 'The range of laps in which a pit stop is strategically viable without losing too much track position or tyre performance.',
  'Undercut': 'Pitting before a rival to use fresh-tyre pace and move ahead when the rival later stops.',
  'Overcut': 'Staying out longer than a rival and gaining time through clear air, tyre management, or a better-timed stop.',
  'Degradation': 'The pace lost as a tyre wears, often expressed as seconds per lap of tyre age.',
  'Safety car': 'A neutralisation that slows the field after a hazard. Gaps compress and pit stops usually cost less race time.',
  'Flag': 'A race-control signal describing track conditions, such as green, yellow, red, or chequered.',
  'Telemetry': 'Recorded car data such as speed, throttle, brake, engine revs, gear, and position.',
  'Throttle': 'How much accelerator input the driver applies, shown here as a percentage.',
  'Brake': 'Whether the recorded brake signal is active at the current replay moment.',
  'RPM': 'Engine revolutions per minute: how quickly the engine is turning.',
  'Race control': 'Official operational messages about flags, incidents, safety cars, track conditions, and penalties.',
  'Median pace': 'The middle clean lap time after laps are ordered from quickest to slowest. It is less distorted by one unusually fast or slow lap.',
  'MAE': 'Mean Absolute Error: the model’s average prediction error in seconds. Lower is better.',
  'Bias': 'The model’s average tendency to predict too high or too low. A value near zero is preferable.',
  'Holdout': 'A session excluded from model training and used afterward to test performance on unseen data.',
  'Pit-lane loss': 'Time lost by entering the pit lane, obeying its speed limit, stopping, and rejoining the circuit.',
  'Warm-up': 'The early phase of a tyre stint while the tyre reaches its working temperature and may be slower.',
} as const

type F1TermName = keyof typeof F1_TERMS

export function F1Term({ term, children = term, chip = false }: { term: F1TermName; children?: ReactNode; chip?: boolean }) {
  const id = `term-${useId().replaceAll(':', '')}`
  const [position, setPosition] = useState<{ left: number; top: number }>()
  const [open, setOpen] = useState(false)
  function positionTooltip(element: HTMLElement) {
    const bounds = element.getBoundingClientRect()
    const halfWidth = Math.min(145, (window.innerWidth - 24) / 2)
    setPosition({ left: Math.max(halfWidth + 12, Math.min(window.innerWidth - halfWidth - 12, bounds.left + bounds.width / 2)), top: bounds.top - 9 })
  }
  function handleKeyDown(event: KeyboardEvent<HTMLSpanElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      event.currentTarget.blur()
    }
  }
  return <span className={`f1-term${chip ? ' glossary-chip' : ''}${open ? ' tooltip-open' : ''}`} tabIndex={0} aria-describedby={id} aria-expanded={open} onMouseEnter={event => positionTooltip(event.currentTarget)} onFocus={event => positionTooltip(event.currentTarget)} onBlur={() => setOpen(false)} onClick={event => { positionTooltip(event.currentTarget); setOpen(value => !value) }} onKeyDown={handleKeyDown}>
    {children}<span id={id} role="tooltip" className="f1-tooltip" style={position}><strong>{term}</strong>{F1_TERMS[term]}</span>
  </span>
}

export function F1Glossary() {
  return <details className="f1-glossary panel">
    <summary><span><span className="eyebrow">NEW TO FORMULA 1?</span>Open the F1 glossary</span><small>Quick terminology reference</small></summary>
    <div className="glossary-terms">
      {(Object.keys(F1_TERMS) as F1TermName[]).map(term => <F1Term key={term} term={term} chip />)}
    </div>
  </details>
}
