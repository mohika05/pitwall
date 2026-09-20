from app.domain.race_state import RaceState


class SnapshotStore:
    def __init__(self) -> None:
        self._snapshots: dict[
            int,
            RaceState,
        ] = {}

    def save(
        self,
        event_index: int,
        state: RaceState,
    ) -> None:
        self._snapshots[
            event_index
        ] = state.model_copy(
            deep=True
        )

    def nearest_at_or_before(
        self,
        event_index: int,
    ) -> tuple[
        int,
        RaceState,
    ] | None:
        eligible = [
            index
            for index in self._snapshots
            if index <= event_index
        ]

        if not eligible:
            return None

        best_index = max(
            eligible
        )

        return (
            best_index,
            self._snapshots[
                best_index
            ].model_copy(
                deep=True
            ),
        )