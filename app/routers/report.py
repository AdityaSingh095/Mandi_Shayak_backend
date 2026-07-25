"""
app/routers/report.py
─────────────────────────────────────────────────────────
GET /api/report/{farmer_crop_id}
Generates & returns the detailed Market Intelligence Advisory Report.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.agents.report_agent import generate_market_advisory_report, MarketAdvisoryReport

router = APIRouter(tags=["Advisory Report"])


@router.get("/report/{farmer_crop_id}", response_model=MarketAdvisoryReport)
async def get_market_advisory_report(
    farmer_crop_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a comprehensive Market Intelligence Advisory Report for export/download.
    Includes Executive Summary, Financial Arbitrage Table, Storage Shrinkage Analysis,
    and 6-Agent Audit Trail.
    """
    try:
        return await generate_market_advisory_report(db, farmer_crop_id)
    except ValueError as ve:
        raise HTTPException(404, str(ve))
    except Exception as e:
        raise HTTPException(500, f"Report generation failed: {e}")
