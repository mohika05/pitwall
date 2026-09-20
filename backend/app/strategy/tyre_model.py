PACE_OFFSET = {"SOFT": -0.6, "MEDIUM": 0.0, "HARD": 0.5, "INTERMEDIATE": 6.0, "WET": 12.0}
WEAR = {"SOFT": 1.35, "MEDIUM": 1.0, "HARD": 0.7, "INTERMEDIATE": 1.0, "WET": 1.0}


def tyre_delta(compound: str, age: float, degradation: float) -> float:
    return PACE_OFFSET.get(compound, 0.0) + max(age, 0) * degradation * WEAR.get(compound, 1.0)
