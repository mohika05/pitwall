"""Deterministic lap-level counterfactuals; never mutate historical events/state."""

from statistics import median

from app.domain.enums import EventType, SafetyCarState
from app.replay.engine import ReplayEngine, state_fingerprint
from app.services.analysis import analyse
from app.strategy.pit_model import pit_loss
from app.strategy.traffic_model import rejoin, traffic_loss
from app.strategy.tyre_model import tyre_delta


def simulate(context, events, request, pace_model=None, sensitivity=True):
    if (
        context.session.session_type.lower() != "race"
        and context.session.session_name.lower() not in ("race", "sprint")
    ):
        raise ValueError("Pit-strategy simulation is available for Race and Sprint sessions")
    engine = ReplayEngine(context, events)
    state = engine.seek_time(request.timestamp)
    driver = state.drivers.get(request.driver_number)
    if driver is None:
        raise ValueError("Driver is not present in this session")
    if driver.dnf or driver.dns or driver.dsq:
        raise ValueError("Cannot branch a retired, non-starting or disqualified driver")
    branch_lap = driver.current_lap
    if request.pit_lap <= branch_lap or request.total_laps <= branch_lap:
        raise ValueError("Pit lap and simulation horizon must follow the driver's completed lap")
    if request.baseline_pit_lap is not None and request.baseline_pit_lap <= branch_lap:
        raise ValueError("Baseline stop must follow the branch lap")
    if request.timestamp != state.replay_timestamp:
        raise ValueError("Branch time must be within recorded session history")
    before = [event for event in events if event.timestamp <= request.timestamp]
    history = analyse(context, before)
    prior = [
        lap
        for lap in history["laps"]
        if lap["driver_number"] == request.driver_number
        and not lap["pit_out"]
        and not lap["neutralized"]
    ]
    if len(prior) < 3:
        raise ValueError("At least three clean completed laps are required before the branch")
    if driver.compound not in ("SOFT", "MEDIUM", "HARD") or request.compound not in (
        "SOFT",
        "MEDIUM",
        "HARD",
    ):
        raise ValueError(
            "Wet/intermediate pace calibration is not available; choose a dry scenario"
        )
    if request.enforce_dry_compounds and context.session.session_name.lower() == "race":
        used = {
            stint["compound"]
            for stint in history["stints"]
            if stint["driver_number"] == request.driver_number
        }
        if len(used | {request.compound}) < 2:
            raise ValueError(
                "The supplied dry-race compound constraint requires two distinct compounds"
            )
    recent = prior[-5:]
    base = median(
        lap["seconds"]
        - tyre_delta(lap["compound"], lap["tyre_age"] or 0, request.degradation)
        + request.fuel_gain * (lap["lap"] - branch_lap)
        for lap in recent
    )
    all_laps = analyse(context, events)["laps"] if request.mode == "historical" else history["laps"]
    future = {
        lap["lap"]: lap
        for lap in all_laps
        if lap["driver_number"] == request.driver_number and lap["lap"] > branch_lap
    }
    stops = [
        event
        for event in events
        if request.mode == "historical"
        and event.event_type == EventType.STINT_STARTED
        and event.driver_number == request.driver_number
        and event.timestamp > request.timestamp
    ]
    # Replace the next recorded stop; preserve later recorded stops explicitly.
    later_stops = {event.lap_number: event.payload["compound"] for event in stops[1:]}
    initial_gaps = {
        number: float(other.gap_to_leader)
        for number, other in state.drivers.items()
        if number != request.driver_number and isinstance(other.gap_to_leader, (int, float))
    }
    own_gap = (
        float(driver.gap_to_leader) if isinstance(driver.gap_to_leader, (int, float)) else None
    )
    baseline_stop = request.baseline_pit_lap
    if request.mode == "forecast" and baseline_stop is None:
        raise ValueError("Decision-time forecasts require an explicit baseline pit lap")
    rows = []
    baseline_elapsed = alternative_elapsed = 0.0
    compound, age = driver.compound, driver.tyre_age or 0
    baseline_compound, baseline_age = compound, age
    warnings = [
        "Lap-level approximation: the branch starts at the driver's last completed lap.",
        "Opponent strategies do not react; overtakes and traffic are approximated.",
        "Rejoin and traffic estimates hold opponents at their branch-point gaps; they are not a predicted finishing order.",
        "Tyre sets and regulation constraints are user-supplied, not verified allocations.",
    ]
    if own_gap is None:
        warnings.append("Numeric gaps unavailable: rejoin position cannot be estimated.")
    model_used = pace_model is not None
    if pace_model is not None:
        base = median(
            lap["seconds"]
            - pace_model(lap["compound"], lap["tyre_age"] or 0)
            + request.fuel_gain * (lap["lap"] - branch_lap)
            for lap in recent
        )
    for lap in range(branch_lap + 1, request.total_laps + 1):
        actual = future.get(lap)
        neutralized = (
            bool(actual and actual["neutralized"])
            if request.mode == "historical"
            else state.safety_car != SafetyCarState.NONE
        )
        stop_compound = request.compound if lap == request.pit_lap else later_stops.get(lap)
        loss = 0.0
        position = None
        traffic = 0.0
        if stop_compound:
            compound, age = stop_compound, 0
            loss = pit_loss(
                request.pit_lane_loss,
                request.stationary_time,
                neutralized,
                request.safety_car_multiplier,
            )
            if own_gap is not None:
                position, distance = rejoin(
                    own_gap + alternative_elapsed - baseline_elapsed, loss, initial_gaps
                )
                traffic = traffic_loss(distance, request.traffic_penalty)
        if own_gap is not None and not stop_compound:
            _, distance = rejoin(own_gap + alternative_elapsed - baseline_elapsed, 0, initial_gaps)
            traffic = traffic_loss(distance, request.traffic_penalty)
        age += 1
        predicted = (
            base
            + tyre_delta(compound, age, request.degradation)
            - request.fuel_gain * (lap - branch_lap)
        )
        if pace_model is not None:
            predicted = base + pace_model(compound, age) - request.fuel_gain * (lap - branch_lap)
        # Replay neutralizations share the observed slowing, without treating it as tyre pace.
        slow = max(0, actual["seconds"] - base) if neutralized and actual else 0
        alternative = (
            predicted + loss + traffic + (request.warmup_loss if stop_compound else 0) + slow
        )
        if request.mode == "historical":
            if actual is None:
                raise ValueError(f"Recorded lap {lap} is missing; shorten the horizon")
            baseline = actual["seconds"]
        else:
            baseline_age += 1
            baseline_loss = 0.0
            if lap == baseline_stop:
                baseline_compound, baseline_age = request.baseline_compound, 1
                baseline_loss = (
                    pit_loss(
                        request.pit_lane_loss,
                        request.stationary_time,
                        neutralized,
                        request.safety_car_multiplier,
                    )
                    + request.warmup_loss
                )
            baseline = (
                base
                + tyre_delta(baseline_compound, baseline_age, request.degradation)
                - request.fuel_gain * (lap - branch_lap)
                + baseline_loss
            )
        baseline_elapsed += baseline
        alternative_elapsed += max(alternative, 1)
        rows.append(
            {
                "lap": lap,
                "baseline": round(baseline_elapsed, 3),
                "alternative": round(alternative_elapsed, 3),
                "delta": round(alternative_elapsed - baseline_elapsed, 3),
                "compound": compound,
                "tyre_age": age,
                "pit": bool(stop_compound),
                "rejoin_position": position,
            }
        )
    delta = alternative_elapsed - baseline_elapsed
    variants = [delta]
    if sensitivity and request.uncertainty:
        for factor in (1 - request.uncertainty, 1 + request.uncertainty):
            altered = request.model_copy(
                update={
                    "degradation": request.degradation * factor,
                    "pit_lane_loss": request.pit_lane_loss * factor,
                    "traffic_penalty": request.traffic_penalty * factor,
                }
            )
            variants.append(
                simulate(context, events, altered, pace_model, sensitivity=False)["delta_seconds"]
            )
    return {
        "trajectory": rows,
        "delta_seconds": round(delta, 3),
        "sensitivity": {
            "optimistic": round(min(variants), 3),
            "central": round(delta, 3),
            "pessimistic": round(max(variants), 3),
        },
        "branch_lap": branch_lap,
        "branch_fingerprint": state_fingerprint(state),
        "model": "validated-ml" if model_used else "deterministic-v1",
        "base_pace": round(base, 3),
        "assumptions": request.model_dump(mode="json"),
        "warnings": warnings,
        "comparison": "Recorded future conditions"
        if request.mode == "historical"
        else "Decision-time information; current conditions held constant",
        "uncertainty_note": "Sensitivity bounds are assumption ranges, not statistical confidence intervals.",
    }
