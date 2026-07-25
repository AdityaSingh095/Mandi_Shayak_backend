"""
app/routers/health.py — GET /api/health
"""

from datetime import datetime
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])

AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    # ── DB ping ───────────────────────────────────────────────────────────
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # ── API ping ──────────────────────────────────────────────────────────
    api_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                AGMARKNET_URL,
                params={"api-key": settings.data_gov_in_api_key, "format": "json", "limit": 1},
            )
            api_status = "reachable" if resp.status_code in (200, 403) else f"http_{resp.status_code}"
    except Exception:
        api_status = "unreachable"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        data_gov_api=api_status,
        database=db_status,
        environment=settings.environment,
        timestamp=datetime.utcnow(),
    )
