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
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Health DB ping error: {e}", exc_info=True)
        db_status = f"error: {str(e)}"

    # ── API ping ──────────────────────────────────────────────────────────
    api_status = "unreachable"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(
                AGMARKNET_URL,
                params={"api-key": settings.data_gov_in_api_key, "format": "json", "limit": 1},
            )
            api_status = "reachable" if resp.status_code in (200, 403) else f"http_{resp.status_code}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Health API ping error: {e}")
        api_status = "unreachable"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        data_gov_api=api_status,
        database=db_status,
        environment=settings.environment,
        timestamp=datetime.utcnow(),
    )
