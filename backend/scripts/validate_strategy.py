"""Run repeatable historical strategy and held-out pace-model validation."""

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean

from app.services.analysis import load_history
from app.strategy.learning import train
from app.strategy.validation import backtest


async def run(args: argparse.Namespace) -> None:
    sessions: list[dict] = []
    errors: list[dict] = []
    for session_key in args.sessions:
        try:
            context, events, _ = await load_history(session_key)
            result = await asyncio.to_thread(backtest, context, events)
            if len(result["cases"]) < args.min_cases:
                raise ValueError(
                    f"Only {len(result['cases'])} supported cases; "
                    f"at least {args.min_cases} are required"
                )
            sessions.append(
                {
                    "session_key": session_key,
                    "year": context.session.year,
                    "country": context.session.country_name,
                    "cases": len(result["cases"]),
                    "skipped": len(result["skipped"]),
                    "mae_seconds": result["mae_seconds"],
                    "baseline_mae_seconds": result["baseline_mae_seconds"],
                    "bias_seconds": result["bias_seconds"],
                    "beats_baseline": result["beats_baseline"],
                }
            )
        except ValueError as exc:
            errors.append({"session_key": session_key, "reason": str(exc)})

    if not sessions:
        raise ValueError("No sessions produced supported validation cases")
    report = {
        "deterministic": {
            "sessions": sessions,
            "unsupported_sessions": errors,
            "supported_sessions": len(sessions),
            "total_cases": sum(item["cases"] for item in sessions),
            "mean_session_mae_seconds": mean(item["mae_seconds"] for item in sessions),
            "mean_session_baseline_mae_seconds": mean(
                item["baseline_mae_seconds"] for item in sessions
            ),
            "sessions_beating_baseline": sum(item["beats_baseline"] for item in sessions),
            "status": "experimental",
        }
    }
    if args.training_sessions:
        model = await train(args.training_sessions)
        report["pace_model"] = {
            key: model[key]
            for key in (
                "algorithm",
                "training_sessions",
                "holdout_session",
                "training_laps",
                "holdout_laps",
                "mae_seconds",
                "baseline_mae_seconds",
                "accepted",
                "limits",
            )
        }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", nargs="+", type=int, required=True)
    parser.add_argument("--training-sessions", nargs="+", type=int)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument(
        "--output", default="../data/processed/strategy-validation.json"
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
