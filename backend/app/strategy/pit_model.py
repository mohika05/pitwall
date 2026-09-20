def pit_loss(lane_loss: float, stationary: float, neutralized: bool, multiplier: float) -> float:
    # Stationary service time is distinct from the net transit loss.
    return lane_loss * (multiplier if neutralized else 1.0) + stationary
