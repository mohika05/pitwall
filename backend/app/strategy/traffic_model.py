def rejoin(gap: float, loss: float, other_gaps: dict[int, float]) -> tuple[int, float | None]:
    projected = gap + loss
    ahead = [value for value in other_gaps.values() if value < projected]
    return len(ahead) + 1, min((projected - value for value in ahead), default=None)


def traffic_loss(distance: float | None, penalty: float) -> float:
    return penalty if distance is not None and 0 <= distance < 2 else 0.0
