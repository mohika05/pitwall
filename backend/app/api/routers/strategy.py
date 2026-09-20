import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.persistence.repositories.workspace_repository import workspace_repository as records
from app.schemas.strategy import StrategyRequest
from app.services.analysis import load_history
from app.strategy.learning import predictor, train
from app.strategy.simulator import simulate

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.post("/simulate")
async def simulation(request: StrategyRequest):
    try:
        context, events, _ = await load_history(request.session_key)
        model = await records.get("model", request.model_id) if request.model_id else None
        result = await asyncio.to_thread(
            simulate, context, events, request, predictor(model, request)
        )
        result.update(id=str(uuid4()), created_at=datetime.now(UTC).isoformat())
        if request.model_id and result["model"] != "validated-ml":
            result["warnings"].append(
                "Requested ML model unavailable, unvalidated or outside permitted data; deterministic fallback used."
            )
        await records.put("scenario", result["id"], result)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/scenarios")
async def scenarios(session_key: int | None = None):
    items = await records.list("scenario")
    return [
        item
        for item in items
        if session_key is None or item["assumptions"]["session_key"] == session_key
    ]


@router.get("/scenarios/{scenario_id}")
async def scenario(scenario_id: UUID):
    result = await records.get("scenario", str(scenario_id))
    if result is None:
        raise HTTPException(404, "Scenario not found")
    return result


class TrainRequest(BaseModel):
    session_keys: list[int] = Field(min_length=2, max_length=30)


@router.post("/models")
async def train_model(request: TrainRequest):
    try:
        return await train(request.session_keys)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/models")
async def models():
    return await records.list("model")


@router.post("/backtest/{session_key}")
async def backtest_session(session_key: int):
    from app.strategy.validation import backtest

    try:
        context, events, _ = await load_history(session_key)
        result = await asyncio.to_thread(backtest, context, events)
        await records.put("backtest", result["id"], result)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
