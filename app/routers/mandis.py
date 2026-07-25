"""
app/routers/mandis.py — GET /api/mandis
app/routers/crops.py  — GET /api/crops
app/routers/history.py — GET /api/history
app/routers/profiles.py — POST, DELETE /api/profile
app/routers/cron.py — POST /api/cron/reevaluate
"""

# ─── mandis.py ───────────────────────────────────────────────────────────────
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Mandi

mandis_router = APIRouter(tags=["Reference Data"])


@mandis_router.get("/mandis")
async def list_mandis(
    state: str = Query(None),
    district: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Mandi).where(Mandi.is_active == True)
    if state:
        q = q.where(Mandi.state == state)
    if district:
        q = q.where(Mandi.district == district)
    result = await db.execute(q.order_by(Mandi.state, Mandi.name))
    mandis = result.scalars().all()
    return {
        "mandis": [
            {
                "id": m.id, "name": m.name, "state": m.state,
                "district": m.district, "latitude": float(m.latitude or 0),
                "longitude": float(m.longitude or 0),
            }
            for m in mandis
        ],
        "total": len(mandis),
    }
