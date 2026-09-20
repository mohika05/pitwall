"""Replay recorded pit choices to measure model error, without fitting to future laps."""

from statistics import mean
from uuid import uuid4

from app.domain.enums import EventType
from app.schemas.strategy import StrategyRequest
from app.services.analysis import analyse
from app.strategy.simulator import simulate


def backtest(context, events):
    analysis = analyse(context, events)
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
        request = StrategyRequest(
            session_key=context.session.session_key,
            driver_number=driver.driver_number,
            timestamp=branch["end"],
            pit_lap=stop.lap_number,
            compound=stop.payload["compound"],
            total_laps=min(max(lap["lap"] for lap in laps), stop.lap_number + 8),
            uncertainty=0,
        )
        try:
            result = simulate(context, events, request, sensitivity=False)
            cases.append(
                {
                    "driver": driver.name_acronym,
                    "pit_lap": stop.lap_number,
                    "horizon_laps": len(result["trajectory"]),
                    "error_seconds": result["delta_seconds"],
                    "branch_fingerprint": result["branch_fingerprint"],
                }
            )
        except ValueError as exc:
            skipped.append({"driver": driver.name_acronym, "reason": str(exc)})
    if not cases:
        raise ValueError("No supported dry pit-stop cases with sufficient pre-stop history")
    return {
        "id": str(uuid4()),
        "session_key": context.session.session_key,
        "cases": cases,
        "skipped": skipped,
        "mae_seconds": mean(abs(case["error_seconds"]) for case in cases),
        "bias_seconds": mean(case["error_seconds"] for case in cases),
        "model": "deterministic-v1",
        "note": "Horizon elapsed-time error following recorded pit choices; this is not counterfactual ground truth.",
    }
