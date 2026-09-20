from fastapi import (
    APIRouter,
    HTTPException,
)

from app.core.exceptions import (
    ExternalDataError,
)
from app.services.session_catalog import (
    session_catalog_service,
)


router = APIRouter(
    prefix="/catalog",
    tags=["catalog"],
)


@router.get(
    "/years"
)
async def catalog_years():
    return {
        "years":
            session_catalog_service
            .years()
    }


@router.get(
    "/{year}"
)
async def year_catalogue(
    year: int,
):
    try:
        return (
            await session_catalog_service
            .year_catalogue(
                year
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except ExternalDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc