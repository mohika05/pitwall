from copy import deepcopy
from datetime import UTC, timedelta
from unittest.mock import AsyncMock

import pytest
from test_engine import START, make_context, make_events

from app.domain.enums import EventType
from app.domain.events import RaceEvent
from app.replay.controller import ReplayController
from app.replay.engine import ReplayEngine, state_fingerprint
from app.schemas.strategy import StrategyRequest
from app.services.analysis import analyse
from app.services.live import merge_rows
from app.strategy.learning import predictor
from app.strategy.simulator import simulate


def race_events():
    events = [
        RaceEvent(
            event_id="stint",
            session_key=1,
            meeting_key=2,
            event_type=EventType.STINT_STARTED,
            timestamp=START,
            driver_number=4,
            lap_number=1,
            payload={
                "compound": "MEDIUM",
                "stint_number": 1,
                "lap_start": 1,
                "tyre_age_at_start": 0,
            },
        )
    ]
    for lap in range(1, 11):
        events.append(
            RaceEvent(
                event_id=f"lap-{lap}",
                session_key=1,
                meeting_key=2,
                event_type=EventType.LAP_COMPLETED,
                timestamp=START + timedelta(seconds=lap * 90),
                driver_number=4,
                lap_number=lap,
                payload={"lap_duration": 90 + lap * 0.06},
            )
        )
    return events


def scenario(**kwargs):
    return StrategyRequest(
        session_key=1,
        driver_number=4,
        timestamp=START + timedelta(seconds=450),
        pit_lap=7,
        total_laps=10,
        **kwargs,
    )


def test_analysis_distinguishes_clean_laps_and_missing_telemetry():
    result = analyse(make_context(), race_events())
    assert len(result["laps"]) == 10
    assert not any(lap["neutralized"] for lap in result["laps"])
    assert result["drivers"][0]["median_pace"] is not None
    assert result["quality"]["total_drivers"] == 1


def test_simulation_is_deterministic_and_does_not_mutate_history():
    events = race_events()
    before = deepcopy(events)
    result = simulate(make_context(), events, scenario())
    assert result == simulate(make_context(), events, scenario())
    assert events == before
    assert result["trajectory"][1]["pit"] is True
    assert result["branch_lap"] == 5
    assert len(result["trajectory"]) == 5


def test_forecast_does_not_use_future_lap_times():
    events = race_events()
    request = scenario(mode="forecast", baseline_pit_lap=9)
    expected = simulate(make_context(), events, request)
    for event in events:
        if event.timestamp > request.timestamp:
            event.payload["lap_duration"] = 180
    assert simulate(make_context(), events, request) == expected


def test_historical_comparison_uses_recorded_baseline():
    result = simulate(make_context(), race_events(), scenario())
    assert result["trajectory"][0]["baseline"] == pytest.approx(90.36)


def test_insufficient_data_and_illegal_pit_are_rejected():
    request = scenario()
    request.timestamp = START + timedelta(seconds=90)
    with pytest.raises(ValueError, match="three clean"):
        simulate(make_context(), race_events(), request)
    request.timestamp = START + timedelta(seconds=720)
    with pytest.raises(ValueError, match="follow"):
        simulate(make_context(), race_events(), request)


def test_live_merge_updates_corrected_lap_without_duplicates():
    old = [{"driver_number": 4, "lap_number": 1, "lap_duration": None}]
    new = [{"driver_number": 4, "lap_number": 1, "lap_duration": 90}]
    assert merge_rows(old, new, "laps") == new
    assert merge_rows(new, new, "laps") == new


def test_model_falls_back_for_heldout_session_or_failed_validation():
    model = {"accepted": False}
    assert predictor(model, scenario()) is None
    model.update(accepted=True, training_sessions=[2], holdout_session=1)
    assert predictor(model, scenario()) is None


async def test_controllers_have_independent_state_and_channels():
    first = ReplayController(1, ReplayEngine(make_context(), make_events()), "a:1")
    second = ReplayController(1, ReplayEngine(make_context(), make_events()), "b:1")
    first._broadcast_state = AsyncMock()
    second._broadcast_state = AsyncMock()
    unchanged = state_fingerprint(second.engine.state)
    await first.seek_index(1)
    assert state_fingerprint(second.engine.state) == unchanged
    assert first.channel != second.channel
    assert first.cache.namespace != second.cache.namespace


async def test_checkpoint_contains_cursor_and_dataset_identity(monkeypatch):
    from app.replay import controller as module

    save = AsyncMock()
    monkeypatch.setattr(module.workspace_repository, "put", save)
    monkeypatch.setattr(module.connection_manager, "broadcast", AsyncMock())
    controller = ReplayController(1, ReplayEngine(make_context(), make_events()), "viewer:1")
    controller.cache.set = AsyncMock()
    await controller.seek_time(START + timedelta(seconds=20))
    payload = save.call_args.args[2]
    assert payload["replay_timestamp"] == (START + timedelta(seconds=20)).isoformat()
    assert payload["dataset_version"] == controller.dataset_version
    assert payload["playing"] is False


async def test_training_uses_a_separate_session_and_persists_validation(monkeypatch):
    from datetime import datetime

    from app.strategy import learning

    def dataset(key):
        return {
            "session": {"session_key": key},
            "start": f"2025-0{key}-01T00:00:00+00:00",
            "end": f"2025-0{key}-01T02:00:00+00:00",
            "laps": [
                {
                    "driver_number": 4,
                    "compound": "MEDIUM",
                    "tyre_age": age,
                    "pit_out": False,
                    "neutralized": False,
                    "seconds": 85 + age * 0.05,
                }
                for age in range(1, 41)
            ],
        }

    load = AsyncMock(side_effect=lambda key: dataset(key))
    save = AsyncMock()
    monkeypatch.setattr(learning, "session_analysis", load)
    monkeypatch.setattr(learning.records, "put", save)
    result = await learning.train([2, 1])
    assert result["training_sessions"] == [1]
    assert result["holdout_session"] == 2
    assert result["accepted"]
    assert result["mae_seconds"] < result["baseline_mae_seconds"]
    request = scenario(mode="forecast", baseline_pit_lap=9)
    request.session_key = 3
    request.timestamp = datetime(2025, 1, 15, tzinfo=UTC)
    assert learning.predictor(result, request) is None  # Model data is in the future.
    assert save.await_count == 1


def test_sensitivity_runs_alternative_assumptions():
    request = scenario()
    result = simulate(make_context(), race_events(), request)
    assert result["sensitivity"]["optimistic"] <= result["delta_seconds"]
    assert result["sensitivity"]["pessimistic"] >= result["delta_seconds"]
    request.uncertainty = 0
    exact = simulate(make_context(), race_events(), request)
    assert exact["sensitivity"]["optimistic"] == exact["sensitivity"]["pessimistic"]


async def test_preparation_deduplicates_running_jobs_and_recovers_interruption(monkeypatch):
    import asyncio

    from app.services import preparation

    service = preparation.PreparationService()
    database = {}

    async def save(kind, key, job):
        database[key] = deepcopy(job)

    async def get(kind, key):
        return database.get(key)

    async def listing(kind, limit):
        return list(database.values())

    started = asyncio.Event()

    async def run(job):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "run", run)
    monkeypatch.setattr(preparation.records, "get", get)
    monkeypatch.setattr(preparation.records, "put", save)
    monkeypatch.setattr(preparation.records, "list", listing)
    one = await service.start(1)
    await started.wait()
    two = await service.start(1)
    assert one == two
    assert len(service.tasks) == 1
    await service.close()
    await service.recover()
    assert database["1"]["state"] == "interrupted"


def test_backtest_follows_recorded_stop_and_reports_horizon_error():
    from app.domain.events import sort_events
    from app.strategy.validation import backtest

    events = race_events()
    events.append(
        RaceEvent(
            event_id="stint-2",
            session_key=1,
            meeting_key=2,
            event_type=EventType.STINT_STARTED,
            timestamp=START + timedelta(seconds=630),
            driver_number=4,
            lap_number=8,
            payload={"compound": "HARD", "stint_number": 2, "lap_start": 8, "tyre_age_at_start": 0},
        )
    )
    result = backtest(make_context(), sort_events(events))
    assert result["cases"][0]["pit_lap"] == 8
    assert result["mae_seconds"] >= 0
