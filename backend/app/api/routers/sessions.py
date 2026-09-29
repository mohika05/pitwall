from fastapi import APIRouter
from sqlalchemy import select

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.race import RaceRecord
from app.persistence.models.session import SessionRecord
from app.persistence.repositories.workspace_repository import (
    workspace_repository,
)

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
)


def _telemetry_session_keys(jobs: list[dict]) -> set[int]:
    return {
        int(job["session_key"])
        for job in jobs
        if job.get("session_key") is not None
        and (
            job.get("telemetry_ready")
            or int(job.get("telemetry_drivers_ready") or 0) > 0
        )
    }


def _session_payload(
    session: SessionRecord,
    meeting_name: str | None,
    telemetry_available: bool,
) -> dict:
    label_parts = [
        str(value)
        for value in (
            session.year,
            session.country_name,
            session.session_name,
        )
        if value is not None
    ]

    return {
        "session_key": session.session_key,
        "meeting_key": session.meeting_key,
        "year": session.year,
        "country": session.country_name,
        "session_name": session.session_name,
        "meeting_name": meeting_name,
        "date_start": session.date_start.isoformat() if session.date_start else None,
        "telemetry_available": telemetry_available,
        "label": " · ".join(label_parts) or f"Session {session.session_key}",
    }


@router.get("")
async def list_sessions():
    """Return ingested session metadata without reading every R2 manifest.

    Telemetry readiness is already recorded by the preparation worker. Reading one
    manifest per session made this directory endpoint perform hundreds of sequential
    object-store requests in production and delayed the entire UI for minutes.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SessionRecord, RaceRecord.meeting_name)
            .outerjoin(RaceRecord, RaceRecord.meeting_key == SessionRecord.meeting_key)
            .order_by(SessionRecord.session_key.desc())
        )
        rows = result.all()

    jobs = await workspace_repository.list("preparation", 1000)
    telemetry = _telemetry_session_keys(jobs)

    return {
        "sessions": [
            _session_payload(
                session,
                meeting_name,
                session.session_key in telemetry,
            )
            for session, meeting_name in rows
        ]
    }
