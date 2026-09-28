"""Small, versioned ridge pace model with race-separated holdout validation."""

from datetime import UTC, datetime
from statistics import median
from uuid import uuid4

import numpy as np

from app.persistence.repositories.workspace_repository import workspace_repository as records
from app.services.analysis import session_analysis

MINIMUM_IMPROVEMENT_FRACTION = 0.05
MODEL_VERSION = 2


def eligible(mae: float, baseline_mae: float) -> bool:
    return mae <= baseline_mae * (1 - MINIMUM_IMPROVEMENT_FRACTION)


def features(compound: str, age: float):
    return [
        1.0,
        float(age),
        float(age) ** 2 / 100,
        float(compound == "SOFT"),
        float(compound == "HARD"),
    ]


def clean_rows(analysis):
    return [
        lap
        for lap in analysis["laps"]
        if lap["compound"] in ("SOFT", "MEDIUM", "HARD")
        and lap["tyre_age"] is not None
        and not lap["pit_out"]
        and not lap["neutralized"]
        and 40 < lap["seconds"] < 200
    ]


def examples(analysis):
    rows = clean_rows(analysis)
    medians = {
        driver: median(lap["seconds"] for lap in rows if lap["driver_number"] == driver)
        for driver in {lap["driver_number"] for lap in rows}
    }
    # Exclude extreme in-laps/outliers; centering controls driver/circuit base pace.
    rows = [lap for lap in rows if abs(lap["seconds"] - medians[lap["driver_number"]]) < 5]
    return (
        rows,
        np.asarray([features(lap["compound"], lap["tyre_age"]) for lap in rows]),
        np.asarray([lap["seconds"] - medians[lap["driver_number"]] for lap in rows]),
    )


async def train(session_keys: list[int]):
    if len(set(session_keys)) < 2:
        raise ValueError("Training requires at least two distinct sessions; the latest is held out")
    sessions = [await session_analysis(key) for key in sorted(set(session_keys))]
    sessions.sort(key=lambda item: item["start"])
    training, holdout = sessions[:-1], sessions[-1]
    datasets = [examples(session) for session in training]
    test_rows, test_x, test_y = examples(holdout)
    if any(len(rows) < 30 for rows, _, _ in datasets) or len(test_rows) < 30:
        raise ValueError("Each session needs at least 30 clean dry laps")
    x = np.concatenate([item[1] for item in datasets])
    y = np.concatenate([item[2] for item in datasets])
    penalty = np.eye(x.shape[1]) * 1.0
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    predicted = test_x @ coefficients
    mae = float(np.mean(np.abs(predicted - test_y)))
    baseline_mae = float(np.mean(np.abs(test_y)))
    model = {
        "id": str(uuid4()),
        "version": MODEL_VERSION,
        "algorithm": "ridge-pace-delta-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "coefficients": coefficients.tolist(),
        "training_sessions": [item["session"]["session_key"] for item in training],
        "holdout_session": holdout["session"]["session_key"],
        "data_end": max(item["end"] for item in sessions),
        "training_laps": len(y),
        "holdout_laps": len(test_y),
        "mae_seconds": mae,
        "baseline_mae_seconds": baseline_mae,
        "accepted": eligible(mae, baseline_mae),
        "minimum_improvement_fraction": MINIMUM_IMPROVEMENT_FRACTION,
        "age_range": [
            min(lap["tyre_age"] for rows, _, _ in datasets for lap in rows),
            max(lap["tyre_age"] for rows, _, _ in datasets for lap in rows),
        ],
        "compounds": sorted({lap["compound"] for rows, _, _ in datasets for lap in rows}),
        "limits": "Predictive association, not a causal tyre model; fuel and traffic remain confounders.",
    }
    await records.put("model", model["id"], model)
    return model


def predictor(model, request):
    if (
        not model
        or model.get("version", 0) < MODEL_VERSION
        or not model.get("accepted", False)
    ):
        return None
    if request.session_key in [*model["training_sessions"], model["holdout_session"]]:
        return None
    if (
        request.mode == "forecast"
        and datetime.fromisoformat(model["data_end"]) >= request.timestamp
    ):
        return None
    if request.compound not in model["compounds"]:
        return None

    def predict(compound, age):
        if (
            compound not in model["compounds"]
            or not model["age_range"][0] <= age <= model["age_range"][1]
        ):
            from app.strategy.tyre_model import tyre_delta

            return tyre_delta(compound, age, request.degradation)
        return float(np.dot(features(compound, age), model["coefficients"]))

    return predict
