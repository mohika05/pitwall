from app.domain.entities import (
    DriverInfo,
    ReplayContext,
    SessionInfo,
)
from app.ingestion.normalizers.common import (
    parse_datetime,
)
from app.ingestion.providers.base import (
    SessionDataBundle,
)

def normalize_context(
    bundle: SessionDataBundle,
) -> ReplayContext:
    raw_session = bundle.session
    date_start = parse_datetime(
        raw_session["date_start"]
    )
    if date_start is None:
        raise ValueError(
            "Session date_start cannot be null"
        )
    session = SessionInfo(
        session_key=int(
            raw_session["session_key"]
        ),
        meeting_key=int(
            raw_session["meeting_key"]
        ),
        year=int(
            raw_session["year"]
        ),
        country_name=raw_session.get(
            "country_name"
        ),
        circuit_short_name=raw_session.get(
            "circuit_short_name"
        ),
        session_name=str(
            raw_session["session_name"]
        ),
        session_type=str(
            raw_session["session_type"]
        ),
        date_start=date_start,
        date_end=parse_datetime(
            raw_session.get("date_end")
        ),
    )
    drivers = [
        DriverInfo(
            driver_number=int(
                raw["driver_number"]
            ),
            full_name=raw.get(
                "full_name"
            ),
            name_acronym=raw.get(
                "name_acronym"
            ),
            team_name=raw.get(
                "team_name"
            ),
            team_colour=raw.get(
                "team_colour"
            ),
            headshot_url=raw.get(
                "headshot_url"
            ),
        )
        for raw in bundle.drivers
    ]
    starting_grid: dict[int, int] = {}
    for row in bundle.starting_grid:
        if (
            row.get("driver_number")
            is not None
            and row.get("position")
            is not None
        ):
            starting_grid[
                int(row["driver_number"])
            ] = int(row["position"])
    return ReplayContext(
        session=session,
        drivers=drivers,
        starting_grid=starting_grid,
    )