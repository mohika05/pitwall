from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.workspace import WorkspaceRecord


class WorkspaceRepository:
    async def get(self, kind: str, key: str) -> dict | None:
        async with AsyncSessionLocal() as db:
            record = await db.get(WorkspaceRecord, (kind, key))
            return record.payload if record else None

    async def put(self, kind: str, key: str, payload: dict) -> None:
        async with AsyncSessionLocal() as db, db.begin():
            statement = insert(WorkspaceRecord).values(kind=kind, key=key, payload=payload)
            await db.execute(
                statement.on_conflict_do_update(
                    index_elements=["kind", "key"],
                    set_={"payload": payload, "updated_at": func.now()},
                )
            )

    async def list(self, kind: str, limit: int = 100) -> list[dict]:
        async with AsyncSessionLocal() as db:
            records = await db.scalars(
                select(WorkspaceRecord)
                .where(WorkspaceRecord.kind == kind)
                .order_by(WorkspaceRecord.updated_at.desc())
                .limit(limit)
            )
            return [record.payload for record in records]


workspace_repository = WorkspaceRepository()
