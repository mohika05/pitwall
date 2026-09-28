"""Replay recorded pit choices to measure model error, without fitting to future laps."""

from statistics import mean, median
from uuid import uuid4

from app.domain.enums import EventType
from app.schemas.strategy import StrategyRequest
from app.services.analysis import analyse
from app.strategy.simulator import simulate


def backtest(context, events):
    analysis = analyse(context, events)
    if any(
        stint["compound"] in ("INTERMEDIATE", "WET")
        for stint in analysis["stints"]
    ):
        raise ValueError("Mixed-weather races are outside dry strategy calibration")
    cases, skipped = [], []
    for driver in context.drivers:
        laps = [lap for lap in analysis["laps"] if lap["driver_number"] == driver.driver_number]
        stops = [
            event
            for event in events
            if event.event_type == EventType.STINT_STARTED
            and event.driver_number == driver.driver_number
            and event.lap_number
            and event.lap_number > 6
            and event.payload.get("compound") in ("SOFT", "MEDIUM", "HARD")
        ]
        if not stops or not laps:
            continue
        stop = stops[0]
        preceding = [lap for lap in laps if lap["lap"] <= stop.lap_number - 3]
        if not preceding:
            continue
        branch = preceding[-1]
        horizon_end = min(max(lap["lap"] for lap in laps), stop.lap_number + 8)
        evaluation = [
            lap for lap in laps if branch["lap"] < lap["lap"] <= horizon_end
        ]
        expected_laps = set(range(branch["lap"] + 1, horizon_end + 1))
        recorded_laps = {lap["lap"] for lap in evaluation}
        if recorded_laps != expected_laps:
            skipped.append(
                {"driver": driver.name_acronym, "reason": "Incomplete evaluation horizon"}
            )
            continue
        if any(
            lap["neutralized"]
            or lap["compound"] not in ("SOFT", "MEDIUM", "HARD")
            or not 40 < lap["seconds"] < 200
            for lap in evaluation
        ):
            skipped.append(
                {
                    "driver": driver.name_acronym,
                    "reason": "Wet, neutralized or abnormal evaluation horizon",
                }
            )
            continue
        request = StrategyRequest(
            session_key=context.session.session_key,
            driver_number=driver.driver_number,
            timestamp=branch["end"],
            pit_lap=stop.lap_number,
            compound=stop.payload["compound"],
            total_laps=horizon_end,
            uncertainty=0,
        )
        try:
            result = simulate(context, events, request, sensitivity=False)
            observed_elapsed = result["trajectory"][-1]["baseline"]
            constant_pace_elapsed = median(lap["seconds"] for lap in preceding[-5:]) * len(
                result["trajectory"]
            )
            constant_pace_elapsed += (
                request.pit_lane_loss + request.stationary_time + request.warmup_loss
            )
            cases.append(
                {
                    "driver": driver.name_acronym,
                    "pit_lap": stop.lap_number,
                    "horizon_laps": len(result["trajectory"]),
                    "error_seconds": result["delta_seconds"],
                    "baseline_error_seconds": round(
                        constant_pace_elapsed - observed_elapsed, 3
                    ),
                    "branch_fingerprint": result["branch_fingerprint"],
                }
            )
        except ValueError as exc:
            skipped.append({"driver": driver.name_acronym, "reason": str(exc)})
    if not cases:
        raise ValueError("No supported dry pit-stop cases with sufficient pre-stop history")
    model_mae = mean(abs(case["error_seconds"]) for case in cases)
    baseline_mae = mean(abs(case["baseline_error_seconds"]) for case in cases)
    return {
        "id": str(uuid4()),
        "session_key": context.session.session_key,
        "cases": cases,
        "skipped": skipped,
        "mae_seconds": model_mae,
        "baseline_mae_seconds": baseline_mae,
        "improvement_seconds": baseline_mae - model_mae,
        "beats_baseline": model_mae < baseline_mae,
        "bias_seconds": mean(case["error_seconds"] for case in cases),
        "model": "deterministic-v1",
        "note": "Horizon elapsed-time error following recorded pit choices; this is not counterfactual ground truth.",
    }
