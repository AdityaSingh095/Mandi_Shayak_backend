"""
app/routers/cron.py — POST /api/cron/reevaluate
Guards with CRON_SECRET bearer token.
Triggered by Vercel cron at 21:30 UTC (03:00 IST) daily.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.agents.monitoring_agent import run_monitoring_batch

router = APIRouter(tags=["Cron"])


@router.post("/cron/reevaluate")
async def cron_reevaluate(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Nightly cron job: re-evaluates all consented farmer crop subscriptions.
    Protected by CRON_SECRET bearer token.
    """
    settings = get_settings()

    # Verify cron secret
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.cron_secret}"
    if auth != expected and settings.is_production:
        raise HTTPException(403, "Unauthorized cron invocation.")

    result = await run_monitoring_batch(db, batch_size=30)
    return result
