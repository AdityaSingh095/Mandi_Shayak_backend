"""
app/routers/planner.py — POST /api/planner/multi-crop
─────────────────────────────────────────────────────────
Multi-Crop Logistics & Warehousing Route Planner Endpoint.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.agents.planner_agent import run_multi_crop_planner

router = APIRouter(tags=["Multi-Crop Planner"])


class MultiCropInputItem(BaseModel):
    crop_name: str
    quantity_quintals: float = 50.0


class MultiCropPlannerRequest(BaseModel):
    state: str = "Madhya Pradesh"
    district: str = "Ujjain"
    crops: List[MultiCropInputItem]
    transport_cost_per_km: float = 18.0
    max_travel_radius_km: float = 250.0


@router.post("/planner/multi-crop")
async def plan_multi_crop(
    request: MultiCropPlannerRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Runs joint multi-crop logistics, warehousing, spatial route mapping,
    and vector trajectory optimization.
    """
    if not request.crops:
        raise HTTPException(400, "At least one crop must be provided in the crops list.")

    crops_payload = [c.model_dump() for c in request.crops]
    
    try:
        result = await run_multi_crop_planner(
            db=db,
            state=request.state,
            district=request.district,
            crops_input=crops_payload,
            transport_cost_per_km=request.transport_cost_per_km,
            max_travel_radius_km=request.max_travel_radius_km,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Multi-crop planner error: {str(e)}")
