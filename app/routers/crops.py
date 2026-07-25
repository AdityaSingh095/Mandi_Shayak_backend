"""
app/routers/crops.py — GET /api/crops
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CropCanon

router = APIRouter(tags=["Reference Data"])


@router.get("/crops")
async def list_crops(db: AsyncSession = Depends(get_db)):
    """Returns all canonical crops for the frontend dropdown."""
    result = await db.execute(select(CropCanon).order_by(CropCanon.canonical_name))
    crops = result.scalars().all()
    return {
        "crops": [
            {
                "id": c.id,
                "canonical_name": c.canonical_name,
                "variety": c.variety,
                "is_perishable": c.is_perishable,
                "shelf_life_days": c.shelf_life_days,
                "aliases": c.get_aliases(),
            }
            for c in crops
        ]
    }
