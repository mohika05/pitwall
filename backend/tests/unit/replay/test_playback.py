import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_engine import START, make_context, make_events

from app.replay import engine as engine_module
from app.replay.controller import ReplayController
from app.replay.engine import ReplayEngine, state_fingerprint


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0.0, before_wake=None)

    async def sleep(delay):
        clock.now += delay
        if clock.before_wake:
            clock.before_wake()

    monkeypatch.setattr(engine_module, "asyncio", SimpleNamespace(
        get_running_loop=lambda: SimpleNamespace(time=lambda: clock.now),
        sleep=sleep,
    ))
    return clock


def test_seek_matches_sequential_state_at_every_index():
    engine = ReplayEngine(make_context(), make_events(), snapshot_interval=1)
    expected = {-1: state_fingerprint(engine.state)}
    for index in range(len(engine.events)):
        expected[index] = state_fingerprint(engine.step())
    for index in [1, -1, 0, 1, 0, -1]:
        assert state_fingerprint(engine.seek_index(index)) == expected[index]


def test_seek_preserves_requested_time_and_clamps_to_history():
    engine = ReplayEngine(make_context(), make_events())
    target = START + timedelta(seconds=45)
    assert engine.seek_time(target).replay_timestamp == target
    assert engine.current_index == 0
    assert engine.seek_time(START - timedelta(seconds=1)).replay_timestamp == START
    assert engine.seek_time(START + timedelta(days=1)).replay_timestamp == make_events()[-1].timestamp


async def test_cursor_advances_between_events_and_pause_does_not_apply_event(clock):
    engine = ReplayEngine(make_context(), make_events())
    cursors = []

    async def tick():
        cursors.append(engine.state.replay_timestamp)
        engine.pause()

    await engine.play(on_tick=tick)
    assert START < cursors[0] < make_events()[0].timestamp
    assert engine.current_index == -1
    assert not engine.is_playing

    clock.before_wake = engine.pause
    await engine.play()
    assert engine.current_index == -1
    assert engine.state.replay_timestamp == cursors[0]


async def test_playback_finishes_and_matches_deterministic_replay(clock):
    engine = ReplayEngine(make_context(), make_events())
    engine.set_speed(100)
    await engine.play()
    assert not engine.is_playing
    assert state_fingerprint(engine.state) == state_fingerprint(
        ReplayEngine(make_context(), make_events()).run_to_end()
    )


async def test_resume_uses_remaining_time_and_speed_changes(clock):
    engine = ReplayEngine(make_context(), make_events())
    engine.seek_time(START + timedelta(seconds=89))

    async def tick():
        engine.set_speed(100)

    await engine.play(on_tick=tick)
    assert clock.now < 0.2
    assert engine.current_index == 1


@pytest.mark.parametrize("speed", [0, -1, float("nan"), float("inf")])
def test_invalid_speeds_are_rejected(speed):
    with pytest.raises(ValueError):
        ReplayEngine(make_context(), make_events()).set_speed(speed)


async def test_controller_reports_start_and_completion(clock):
    engine = ReplayEngine(make_context(), make_events())
    engine.set_speed(100)
    controller = ReplayController(1, engine)
    states = []

    async def broadcast(force=False):
        states.append(controller.playing)

    controller._broadcast_state = broadcast
    assert (await controller.play())["playing"]
    await controller._play_task
    assert states[0] is True
    assert states[-1] is False


async def test_pause_cancels_pending_event_and_seek_increments_revision():
    controller = ReplayController(1, ReplayEngine(make_context(), make_events()))
    controller._broadcast_state = AsyncMock()
    await controller.play()
    await asyncio.sleep(0)
    await controller.pause()
    assert controller.engine.current_index == -1
    assert not controller.playing
    result = await controller.seek_time(START + timedelta(seconds=45))
    assert result["revision"] == 1
    assert result["event_index"] == 0
    assert not result["playing"]
    assert (await controller.reset())["revision"] == 2


def test_equal_timestamp_events_are_ordered_independently_of_input():
    events = make_events()
    events[1].timestamp = events[0].timestamp
    first = ReplayEngine(make_context(), events, snapshot_interval=1)
    second = ReplayEngine(make_context(), list(reversed(events)))
    expected = state_fingerprint(first.run_to_end())
    assert state_fingerprint(second.seek_time(events[0].timestamp)) == expected
    first.seek_index(-1)
    assert state_fingerprint(first.seek_time(events[0].timestamp)) == expected


async def test_empty_playback_finishes_without_advancing_clock(clock):
    engine = ReplayEngine(make_context(), [])
    await engine.play()
    assert not engine.is_playing
    assert engine.state.replay_timestamp == START
