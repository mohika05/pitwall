from datetime import datetime

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.session_repository import (
    SessionRepository,
)
from app.services.telemetry import (
    telemetry_service,
)


router = APIRouter(
    prefix="/telemetry",
    tags=["telemetry"],
)


@router.get(
    "/{session_key}/snapshot"
)
async def telemetry_snapshot(
    session_key: int,
    timestamp: datetime,
    driver: str | None = Query(
        default=None,
        min_length=2,
        max_length=3,
    ),
    tolerance_seconds: float = Query(
        default=2.0,
        ge=0.1,
        le=10.0,
    ),
):
    async with AsyncSessionLocal() as db:
        try:
            context = await SessionRepository(
                db
            ).get_replay_context(
                session_key
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

    selected_driver = driver.upper() if driver else None

    async def load_driver(
        session_driver,
    ):
        if not session_driver.name_acronym:
            return None

        try:
            loader = (
                telemetry_service.snapshot
                if selected_driver is None
                or session_driver.name_acronym.upper() == selected_driver
                else telemetry_service.position_snapshot
            )
            snapshot = await loader(
                session_key=session_key,
                driver=session_driver.name_acronym,
                timestamp=timestamp,
                tolerance_seconds=tolerance_seconds,
            )

        except (
            FileNotFoundError,
            ValueError,
        ) as exc:
            return {
                "driver_number": (
                    session_driver.driver_number
                ),
                "driver": (
                    session_driver.name_acronym
                ),
                "error": str(exc),
                "car": None,
                "position": None,
            }

        snapshot[
            "driver_number"
        ] = session_driver.driver_number

        return snapshot

    # Loading every driver's full car and position frame concurrently exceeds
    # the 512 MiB deployment tier. Keep peak memory bounded and return full car
    # telemetry only for the driver the viewer selected.
    results = []
    for session_driver in context.drivers:
        results.append(await load_driver(session_driver))

    return {
        "session_key": session_key,
        "timestamp": (
            timestamp.isoformat()
        ),
        "drivers": [
            result
            for result in results
            if result is not None
        ],
    }


@router.get(
    "/{session_key}/drivers/"
    "{driver}/snapshot"
)
async def driver_telemetry_snapshot(
    session_key: int,
    driver: str,
    timestamp: datetime,
    tolerance_seconds: float = Query(
        default=2.0,
        ge=0.1,
        le=10.0,
    ),
):
    try:
        return await telemetry_service.snapshot(
            session_key=(
                session_key
            ),
            driver=driver,
            timestamp=timestamp,
            tolerance_seconds=(
                tolerance_seconds
            ),
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{session_key}/drivers/"
    "{driver}/window"
)
async def driver_telemetry_window(
    session_key: int,
    driver: str,
    start: datetime,
    end: datetime,
    max_points: int = Query(
        default=500,
        ge=10,
        le=2000,
    ),
):
    try:
        return await telemetry_service.window(
            session_key=(
                session_key
            ),
            driver=driver,
            start=start,
            end=end,
            max_points=max_points,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

@router.get(
    "/{session_key}/track"
)
async def telemetry_track(
    session_key: int,
    driver: str | None = Query(
        default=None,
        min_length=2,
        max_length=3,
    ),
    max_points: int = Query(
        default=400,
        ge=100,
        le=1000,
    ),
):
    if driver is None:
        candidates = await telemetry_service.available_drivers(session_key)
        for candidate in candidates:
            try:
                return await telemetry_service.track_shape(
                    session_key=session_key, driver=candidate,
                    max_points=max_points,
                )
            except (FileNotFoundError, ValueError):
                continue
        raise HTTPException(404, "No complete circuit lap is available; prepare telemetry first")
    try:
        return await telemetry_service.track_shape(
            session_key=(
                session_key
            ),
            driver=driver,
            max_points=max_points,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
