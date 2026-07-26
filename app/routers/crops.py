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
    if not crops:
        return {
            "crops": [
                {"id": 1, "canonical_name": "Wheat", "variety": "Sharbati", "is_perishable": False, "shelf_life_days": 180, "aliases": ["Kanak", "Gehun"]},
                {"id": 2, "canonical_name": "Potato", "variety": "Red", "is_perishable": True, "shelf_life_days": 90, "aliases": ["Aloo"]},
                {"id": 3, "canonical_name": "Soybean", "variety": "Yellow", "is_perishable": False, "shelf_life_days": 120, "aliases": ["Soyabean"]},
                {"id": 4, "canonical_name": "Mustard", "variety": "Bold", "is_perishable": False, "shelf_life_days": 150, "aliases": ["Sarson"]},
                {"id": 5, "canonical_name": "Gram", "variety": "Desi", "is_perishable": False, "shelf_life_days": 150, "aliases": ["Chana"]},
                {"id": 6, "canonical_name": "Onion", "variety": "Red", "is_perishable": True, "shelf_life_days": 90, "aliases": ["Pyaz"]},
                {"id": 7, "canonical_name": "Tomato", "variety": "Hybrid", "is_perishable": True, "shelf_life_days": 14, "aliases": ["Tamatar"]},
                {"id": 8, "canonical_name": "Paddy", "variety": "Common", "is_perishable": False, "shelf_life_days": 180, "aliases": ["Dhan"]}
            ]
        }
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
