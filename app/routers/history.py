"""
app/routers/history.py — GET /api/history
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.agents.history_agent import get_price_history

router = APIRouter(tags=["Analytics"])


@router.get("/history")
async def price_history(
    crop_id: int = Query(...),
    mandi_ids: str = Query(None, description="Comma-separated mandi IDs"),
    state: str = Query(None, description="Filter mandis dynamically by state name"),
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns price series for frontend chart rendering.
    Supports querying mandis dynamically by state or comma-separated mandi_ids.
    """
    mandi_id_list = []
    if mandi_ids:
        try:
            mandi_id_list = [int(x.strip()) for x in mandi_ids.split(",")]
        except ValueError:
            raise HTTPException(422, "mandi_ids must be comma-separated integers")

    result = await get_price_history(db, crop_id, mandi_id_list, days, state=state)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result
