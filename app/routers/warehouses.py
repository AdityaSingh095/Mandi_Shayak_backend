"""
app/routers/warehouses.py — GET /api/warehouses
─────────────────────────────────────────────────────────
Returns WDRA-registered Warehouses, Grain Silos, and Cold Storages
with exact geographic coordinates for distribution & storage route planning.
"""

from typing import Optional
from fastapi import APIRouter, Query
from app.warehouse_data import get_warehouses, WAREHOUSES_DATA

router = APIRouter(tags=["Warehouses"])


@router.get("/warehouses")
async def list_warehouses(
    state: Optional[str] = Query(None, description="Filter by State (e.g. Madhya Pradesh, Maharashtra)"),
    district: Optional[str] = Query(None, description="Filter by District (e.g. Ujjain, Nashik)"),
    crop_name: Optional[str] = Query(None, description="Filter by Supported Crop (e.g. Wheat, Potato)"),
    is_cold_storage: Optional[bool] = Query(None, description="Filter temperature controlled facilities"),
):
    """
    Returns list of registered warehouses and cold storage hubs
    including latitude, longitude, capacities, and daily rates.
    """
    facilities = get_warehouses(state, district, crop_name, is_cold_storage)
    return {
        "count": len(facilities),
        "warehouses": facilities
    }
