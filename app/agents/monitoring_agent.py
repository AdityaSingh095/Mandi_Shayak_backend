"""
app/agents/monitoring_agent.py
─────────────────────────────────────────────────────────
Agent 7: Cron batch re-evaluator.
Runs nightly — re-evaluates all consented farmer crop subscriptions
and writes in-app notification if recommendation changed meaningfully.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FarmerCrop, FarmerProfile, AuditTrail

logger = logging.getLogger(__name__)

# ── Meaningful change transition table ───────────────────────────────────────
ALWAYS_NOTIFY_TRANSITIONS = {
    ("HOLD", "SELL_NOW"),
    ("HOLD", "TRAVEL"),
    ("MONITOR", "SELL_NOW"),
    ("MONITOR", "TRAVEL"),
    ("MONITOR", "HOLD"),
    ("SELL_LOCAL", "TRAVEL"),
    ("SELL_LOCAL", "HOLD"),
}


def _recommendation_changed_meaningfully(prev: str | None, new: str) -> bool:
    """Returns True if the recommendation change warrants a notification."""
    if prev is None:
        return True  # First recommendation — always notify
    if prev == new:
        return False
    return (prev, new) in ALWAYS_NOTIFY_TRANSITIONS or prev != new


async def _send_in_app_notification(db: AsyncSession, farmer_crop: FarmerCrop, recommendation: str, headline: str):
    """Stores notification in FarmerProfile.pending_notification JSONB/text field."""
    if not farmer_crop.farmer_id:
        return
    profile = await db.get(FarmerProfile, farmer_crop.farmer_id)
    if not profile:
        return

    notification = {
        "recommendation": recommendation,
        "headline": headline,
        "generated_at": datetime.utcnow().isoformat(),
        "read": False,
    }
    profile.pending_notification = json.dumps(notification)
    profile.updated_at = datetime.utcnow()


class CronResult:
    def __init__(self):
        self.processed = 0
        self.notified = 0
        self.errors = 0


async def run_monitoring_batch(db: AsyncSession, batch_size: int = 30) -> dict:
    """
    Process up to batch_size consented farmer crops.
    Ordered by oldest last_recommendation_at first (None first = never evaluated).
    """
    from app.agents.pipeline import run_full_pipeline

    result = CronResult()

    # Fetch eligible crops
    eligible_q = (
        select(FarmerCrop)
        .join(FarmerProfile, FarmerCrop.farmer_id == FarmerProfile.id)
        .where(
            FarmerProfile.consent_given == True,
            FarmerProfile.deleted_at == None,
        )
        .order_by(FarmerCrop.last_recommendation_at.asc().nulls_first())
        .limit(batch_size)
    )
    res = await db.execute(eligible_q)
    farmer_crops = res.scalars().all()

    for fc in farmer_crops:
        try:
            ctx = await run_full_pipeline(db, str(fc.id))

            new_rec = ctx.recommendation.recommendation if ctx.recommendation else None
            old_rec = fc.last_recommendation

            if new_rec and _recommendation_changed_meaningfully(old_rec, new_rec):
                await _send_in_app_notification(
                    db, fc, new_rec, ctx.recommendation.headline if ctx.recommendation else ""
                )
                result.notified += 1
                logger.info(f"Notified farmer_crop {fc.id}: {old_rec} → {new_rec}")

            result.processed += 1

        except Exception as e:
            result.errors += 1
            logger.error(f"Cron error for farmer_crop {fc.id}: {e}")

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Cron DB commit failed: {e}")

    return {
        "processed": result.processed,
        "notified": result.notified,
        "errors": result.errors,
        "completed_at": datetime.utcnow().isoformat(),
    }
