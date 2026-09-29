import { test, expect } from '@playwright/test'
const start = '2025-10-05T12:00:00Z'
const analysis = {
  session: { session_key: 1, year: 2025, country_name: 'Singapore', session_name: 'Race', session_type: 'Race' },
  start, end: '2025-10-05T13:00:00Z',
  drivers: [{ driver_number: 4, name_acronym: 'NOR', full_name: 'Lando Norris', team_colour: 'FF8700', laps: 20, best: 90, median_pace: 91 }, { driver_number: 63, name_acronym: 'RUS', team_colour: '27F4D2', laps: 20, best: 89, median_pace: 90 }],
  laps: [4, 63].flatMap((number) => [1, 2, 3, 4, 5].map(lap => ({ driver_number: number, driver: number === 4 ? 'NOR' : 'RUS', lap, seconds: 90 + lap, start, end: '2025-10-05T12:01:30Z', compound: 'MEDIUM', tyre_age: lap, stint: 1, pit_out: false, neutralized: false, sectors: [30, 30, 30], stage: null }))),
  stints: [{ driver_number: 4, driver: 'NOR', compound: 'MEDIUM', stint_number: 1, lap_start: 1, lap_end: 20 }], timeline: [], qualifying: [], official_result: [],
  quality: { source: 'Test fixture', telemetry_drivers: ['NOR', 'RUS'], total_drivers: 2, note: 'Fixture data' },
}
test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname.replace('/api', '')
    let body: unknown = []
    if (path === '/sessions') body = { sessions: [{ session_key: 1, year: 2025, country: 'Singapore', meeting_name: 'Singapore Grand Prix', session_name: 'Race', telemetry_available: true, label: '2025 · Singapore · Race' }] }
    else if (path === '/catalog/years') body = { years: [2025] }
    else if (path === '/catalog/2025') body = { year: 2025, meetings: [{ meeting_key: 2, meeting_name: 'Singapore Grand Prix', sessions: [{ session_key: 1, session_name: 'Race', ingested: true }, { session_key: 2, session_name: 'Qualifying', ingested: false }] }] }
    else if (path === '/analysis/1') body = analysis
    else if (path.endsWith('/track')) body = { session_key: 1, lap_number: 1, points: [{ x: 0, y: 0 }, { x: 1000, y: 0 }, { x: 1500, y: 1000 }, { x: 0, y: 1500 }] }
    else if (path.endsWith('/window')) body = { car: [{ Date: start, Speed: 100, Throttle: 60 }, { Date: '2025-10-05T12:01:00Z', Speed: 300, Throttle: 100 }] }
    return route.fulfill({ json: body })
  })
  await page.routeWebSocket('**/ws/replay/**', socket => {
    socket.send(JSON.stringify({ type: 'race_state', session_key: 1, payload: { revision: 0, event_index: 10, total_events: 100, playing: false, speed: 1, state: { session_key: 1, meeting_key: 2, current_lap: 3, replay_timestamp: start, drivers: { 4: { driver_number: 4, name_acronym: 'NOR', position: 1, compound: 'MEDIUM', tyre_age: 3, current_lap: 3, team_colour: 'FF8700' } } } } }))
  })
})
test('all three workspaces load and remain within the viewport', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Singapore Grand Prix' })).toBeVisible()
  await expect(page.getByText('Race Order', { exact: true })).toBeVisible()
  await page.screenshot({ path: `test-results/replay-${test.info().project.name}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: /Analyze/ }).click()
  await expect(page.getByRole('heading', { name: 'Find the difference.' })).toBeVisible()
  await page.screenshot({ path: `test-results/analysis-${test.info().project.name}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: /Strategy/ }).click()
  await expect(page.getByRole('heading', { name: 'Change the call.' })).toBeVisible()
  await expect(page.getByText('Experimental dry-race model')).toBeVisible()
  await expect(page.getByText('Choose the decision moment')).toBeVisible()
  await page.screenshot({ path: `test-results/strategy-${test.info().project.name}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('glossary terms support pointer, keyboard and touch-style activation', async ({ page }) => {
  await page.goto('/')
  await page.getByText('Open the F1 glossary').click()
  const term = page.locator('.glossary-chip').filter({ hasText: /^Undercut/ })
  await term.click()
  await expect(term.getByRole('tooltip')).toBeVisible()
  await expect(term).toHaveAttribute('aria-expanded', 'true')
  await term.press('Escape')
  await expect(term).toHaveAttribute('aria-expanded', 'false')
})

test('model lab uses named races and explains the holdout', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Strategy/ }).click()
  await expect(page.getByLabel('Historical race')).toContainText('2025')
  await expect(page.getByText('reserves the newest selected race as a')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Train & test model' })).toBeDisabled()
})

test('duplicate model runs are compact and never expose raw archived session IDs', async ({ page }) => {
  const repeated = { id: 'model-one', version: 2, accepted: true, mae_seconds: 0.77, baseline_mae_seconds: 0.9, training_sessions: [1], holdout_session: 1, training_laps: 200, limits: 'Fixture' }
  await page.route('**/api/strategy/models', route => route.fulfill({ json: [repeated, { ...repeated, id: 'model-two', mae_seconds: 0.78 }] }))
  await page.goto('/')
  await page.getByRole('button', { name: /Strategy/ }).click()
  await expect(page.getByRole('option', { name: /Validated ML/ })).toHaveCount(1)
  await expect(page.getByText('1 historical race', { exact: true })).toHaveCount(1)
  await expect(page.getByText(/Archived session/)).toHaveCount(0)
})

test('strategy errors are translated into useful guidance', async ({ page }) => {
  await page.route('**/api/replay/1/pause*', route => route.fulfill({ json: { replay_timestamp: '2025-10-05T12:05:00Z' } }))
  await page.route('**/api/strategy/simulate', route => route.fulfill({ status: 400, json: { detail: 'Mixed-weather races are outside dry strategy calibration' } }))
  await page.goto('/')
  await page.getByRole('button', { name: /Strategy/ }).click()
  await page.getByRole('button', { name: 'Branch & simulate →' }).click()
  await expect(page.getByRole('alert')).toContainText('Replay and analysis are still available')
  await expect(page.getByRole('alert')).not.toContainText('API 400')
})

test('strategy submission renders a comparison and unavailable sessions stay disabled', async ({ page }) => {
  await page.route('**/api/replay/1/pause*', route => route.fulfill({ json: { replay_timestamp: '2025-10-05T12:05:00Z' } }))
  await page.route('**/api/strategy/simulate', route => route.fulfill({ json: {
    id: 'scenario-test', created_at: start, delta_seconds: -2.5, branch_lap: 3, model: 'deterministic-v1',
    trajectory: [{ lap: 4, baseline: 90, alternative: 89, delta: -1, compound: 'HARD', tyre_age: 1, pit: true, rejoin_position: 4 }, { lap: 5, baseline: 180, alternative: 177.5, delta: -2.5, compound: 'HARD', tyre_age: 2, pit: false, rejoin_position: null }],
    sensitivity: { optimistic: -4, central: -2.5, pessimistic: 1 },
    assumptions: { name: 'Earlier stop', session_key: 1, mode: 'historical', pit_lap: 4, compound: 'HARD' },
    warnings: ['Fixture assumptions'], comparison: 'Recorded future conditions', uncertainty_note: 'Scenario range',
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: /Strategy/ }).click()
  await page.getByLabel('Pit lap', { exact: true }).fill('4')
  await page.getByLabel('Simulate through lap').fill('5')
  await page.getByRole('button', { name: 'Branch & simulate →' }).click()
  await expect(page.getByText('-2.50s', { exact: true })).toBeVisible()
  await page.locator('.race-browser summary').click()
  const unavailable = page.getByRole('button', { name: /Qualifying/ })
  await expect(unavailable).toBeDisabled()
  await expect(unavailable).toContainText('Awaiting archive')
})

test('qualifying shows recorded stages and excludes race-only pit simulation', async ({ page }) => {
  await page.route('**/api/analysis/1', route => route.fulfill({ json: {
    ...analysis,
    session: { ...analysis.session, session_name: 'Qualifying', session_type: 'Qualifying' },
    laps: analysis.laps.map(lap => ({ ...lap, stage: 'Q1' })),
    qualifying: [{ driver_number: 4, Q1: 90, Q2: 89.5, Q3: 89, position: 1 }],
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: /Analyze/ }).click()
  await expect(page.getByText('Qualifying progression · official stage times')).toBeVisible()
  await page.getByLabel('Qualifying stage').selectOption('Q1')
  await expect(page.getByText('Q3 time recorded')).toBeVisible()
  await page.getByRole('button', { name: /Strategy/ }).click()
  await expect(page.getByText('Pit strategy is available for Race and Sprint.', { exact: false })).toBeVisible()
})
