import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'
import { useRaceStore } from '../src/stores/raceStore.ts'
import { RaceWebSocket } from '../src/lib/websocket.ts'

const payload = (session = 1, revision = 0) => ({
  revision,
  state: {
    session_key: session, meeting_key: 2, current_lap: 0,
    replay_timestamp: '2025-01-01T00:00:01Z',
    drivers: { 4: { driver_number: 4, name_acronym: 'NOR', position: 1 } },
  },
  event_index: 0, total_events: 2, playing: false, speed: 1,
})
const telemetry = (session = 1) => ({ session_key: session, timestamp: '2025-01-01T00:00:01Z', drivers: [] })
const store = () => useRaceStore.getState()

beforeEach(() => {
  useRaceStore.setState(useRaceStore.getInitialState())
  store().setSessionKey(1)
})

test('same-session selection preserves playback and driver state', () => {
  store().applyRealtimeState(payload())
  store().setSessionKey(1)
  assert.equal(store().selectedDriver, 'NOR')
  assert.equal(store().eventIndex, 0)
})

test('late race and telemetry data cannot overwrite a new session', () => {
  store().setSessionKey(2)
  store().applyRealtimeState(payload(1))
  store().setTelemetry(telemetry(1), 0)
  assert.equal(store().state, null)
  assert.equal(store().telemetry, null)
})

test('seeking clears telemetry and rejects responses from the previous revision', () => {
  store().applyRealtimeState(payload())
  store().setTelemetry(telemetry(), 0)
  assert.ok(store().telemetry)
  store().applyRealtimeState(payload(1, 1))
  assert.equal(store().telemetry, null)
  store().setTelemetry(telemetry(), 0)
  assert.equal(store().telemetry, null)
  store().setTelemetry(telemetry(), 1)
  assert.ok(store().telemetry)
})

test('reconnected backend can restart its revision counter', () => {
  store().applyRealtimeState(payload(1, 4))
  store().applyRealtimeState(payload(1, 0))
  assert.equal(store().revision, 0)
})

test('obsolete socket callbacks are ignored, even after returning to the same session', () => {
  const sockets = []
  class FakeWebSocket {
    static OPEN = 1
    static CONNECTING = 0
    readyState = 0
    constructor() { sockets.push(this) }
    close() { this.readyState = 3 }
  }
  const previous = globalThis.WebSocket
  globalThis.WebSocket = FakeWebSocket
  try {
    const connection = new RaceWebSocket(1)
    connection.connect()
    const socket = sockets[0]
    const lateOpen = socket.onopen
    const lateMessage = socket.onmessage
    const lateClose = socket.onclose
    connection.disconnect()
    store().setSessionKey(2)
    store().setSessionKey(1)
    lateOpen()
    lateMessage({ data: JSON.stringify({ type: 'race_state', session_key: 1, payload: payload() }) })
    lateClose()
    assert.equal(store().state, null)
    assert.equal(store().connected, false)
    assert.equal(socket.onmessage, null)
  } finally {
    globalThis.WebSocket = previous
  }
})

test('reconnection rejects pending telemetry even if the revision number repeats', () => {
  store().applyRealtimeState(payload())
  const oldEpoch = store().streamEpoch
  store().setConnected(true)
  store().setTelemetry(telemetry(), 0, oldEpoch)
  assert.equal(store().telemetry, null)
  store().setTelemetry(telemetry(), 0, store().streamEpoch)
  assert.ok(store().telemetry)
})
