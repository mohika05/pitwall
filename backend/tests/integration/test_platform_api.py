"""Opt-in checks against the local migrated PostgreSQL and Redis services."""

import os
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from app.main import app
from app.persistence.database import AsyncSessionLocal, engine
from app.persistence.models.workspace import WorkspaceRecord
from app.replay.controller import replay_registry

pytestmark = pytest.mark.skipif(
    os.getenv("PITWALL_INTEGRATION") != "1", reason="Requires local PostgreSQL/Redis"
)


async def test_real_session_analysis_isolated_replay_and_scenario():
    identifiers = [str(uuid4()), str(uuid4())]
    scenario_id = None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            sessions = await client.get("/sessions")
            assert sessions.status_code == 200, sessions.text
            key = sessions.json()["sessions"][0]["session_key"]
            response = await client.get(f"/analysis/{key}")
            assert response.status_code == 200, response.text
            analysis = response.json()
            assert analysis["laps"] and analysis["drivers"]
            first = f"/replay/{key}"
            before = await client.get(first + "/state", params={"viewer_id": identifiers[1]})
            assert before.status_code == 200, before.text
            seek = await client.post(
                first + "/seek/index",
                params={"viewer_id": identifiers[0]},
                json={"event_index": 10},
            )
            assert seek.status_code == 200, seek.text
            after = await client.get(first + "/state", params={"viewer_id": identifiers[1]})
            assert after.json()["status"]["event_index"] == before.json()["status"]["event_index"]
            controller = replay_registry._controllers.pop(f"{identifiers[0]}:{key}")
            restored = await replay_registry.get(key, identifiers[0])
            assert (
                restored.engine.state.replay_timestamp == controller.engine.state.replay_timestamp
            )
            assert not restored.playing
            driver = next(d for d in analysis["drivers"] if d["laps"] > 20)
            laps = sorted(
                [
                    lap
                    for lap in analysis["laps"]
                    if lap["driver_number"] == driver["driver_number"]
                ],
                key=lambda l: l["lap"],
            )
            branch = laps[10]
            simulated = await client.post(
                "/strategy/simulate",
                json={
                    "session_key": key,
                    "driver_number": driver["driver_number"],
                    "timestamp": branch["end"],
                    "pit_lap": branch["lap"] + 2,
                    "total_laps": branch["lap"] + 8,
                    "name": "Integration check",
                },
            )
            assert simulated.status_code == 200, simulated.text
            scenario_id = simulated.json()["id"]
            saved = await client.get(f"/strategy/scenarios/{scenario_id}")
            assert saved.status_code == 200
            assert len(saved.json()["trajectory"]) == 8
            track = await client.get(f"/telemetry/{key}/track")
            assert track.status_code == 200, track.text
            assert len(track.json()["points"]) >= 100
            assert datetime.fromisoformat(branch["end"])
    finally:
        for key, controller in list(replay_registry._controllers.items()):
            if any(key.startswith(identifier) for identifier in identifiers):
                await controller.pause()
                replay_registry._controllers.pop(key)
        async with AsyncSessionLocal() as db, db.begin():
            for identifier in identifiers:
                await db.execute(
                    delete(WorkspaceRecord).where(
                        WorkspaceRecord.kind == "replay", WorkspaceRecord.key.startswith(identifier)
                    )
                )
            if scenario_id:
                await db.execute(
                    delete(WorkspaceRecord).where(
                        WorkspaceRecord.kind == "scenario", WorkspaceRecord.key == scenario_id
                    )
                )
        await engine.dispose()
