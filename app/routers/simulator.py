"""
app/routers/simulator.py
─────────────────────────────────────────────────────────
POST /api/simulator/sell-window
Calculates optimal sell timing considering moisture shrinkage & storage fees.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from app.agents.simulator_agent import run_sell_window_simulation, SimulationResult

router = APIRouter(tags=["Harvest Simulator"])


class SimulationRequest(BaseModel):
    crop_name: str
    quantity_quintals: float = 50.0
    current_price: float = 2400.0
    trend_momentum_pct_per_day: float = 0.5
    storage_fee_per_qtl_day: float = 1.0
    projection_days: int = 14


@router.post("/simulator/sell-window", response_model=SimulationResult)
async def simulate_sell_window(req: SimulationRequest):
    """
    Returns day-by-day projected net revenue curve accounting for storage shrinkage & fees.
    Zero external paid APIs — 100% fast, deterministic calculation.
    """
    return run_sell_window_simulation(
        crop_name=req.crop_name,
        quantity_quintals=req.quantity_quintals,
        current_price=req.current_price,
        trend_momentum_pct_per_day=req.trend_momentum_pct_per_day,
        storage_fee_per_qtl_day=req.storage_fee_per_qtl_day,
        projection_days=req.projection_days,
    )
