"""
app/agents/pipeline.py
─────────────────────────────────────────────────────────
Orchestrates the full agent pipeline:
Agent1 (Intake) → Agent3 (Normalize) → Agent2 (Prices)
→ Agent4 (Trend) → Agent5 (Arbitrage) → Agent6 (Recommend)
Also saves audit trail to DB after each run.
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import PipelineContext
from app.agents.intake_agent import run_intake_agent
from app.agents.normalization_agent import run_normalization_agent
from app.agents.price_fetch_agent import run_price_fetch_agent
from app.agents.trend_agent import run_trend_agent
from app.agents.arbitrage_agent import run_arbitrage_agent
from app.agents.recommendation_agent import run_recommendation_agent
from app.config import load_runtime_config
from app.models import AuditTrail, FarmerCrop
from app.schemas import IntakeRequest

logger = logging.getLogger(__name__)


async def run_intake_pipeline(
    db: AsyncSession, request: IntakeRequest
) -> PipelineContext:
    """
    Runs only the Intake + Normalization agents.
    Called by POST /api/intake — returns ctx before price fetching.
    """
    await load_runtime_config(db)
    ctx = await run_intake_agent(db, request)
    ctx = await run_normalization_agent(db, ctx, request.crop_raw_name)
    return ctx


async def run_full_pipeline(
    db: AsyncSession,
    farmer_crop_id: str,
    transport_override: float | None = None,
    quantity_override: float | None = None,
) -> PipelineContext:
    """
    Full pipeline: loads existing farmer_crop context from DB,
    then runs Price → Trend → Arbitrage → Recommendation.
    Called by POST /api/analyze and the cron agent.
    """
    await load_runtime_config(db)

    # ── Rebuild context from DB ───────────────────────────────────────────
    ctx = await _load_context_from_db(db, farmer_crop_id)
    if not ctx:
        raise ValueError(f"farmer_crop_id {farmer_crop_id} not found")

    if transport_override:
        ctx.transport_cost_per_km = transport_override
    if quantity_override:
        ctx.quantity_quintals = quantity_override

    ctx.session_id = str(uuid.uuid4())

    # ── Agent pipeline ────────────────────────────────────────────────────
    ctx = await run_price_fetch_agent(db, ctx)
    ctx = await run_trend_agent(ctx)
    ctx = await run_arbitrage_agent(ctx)
    ctx = await run_recommendation_agent(ctx)

    # ── Persist audit trail ───────────────────────────────────────────────
    await _save_audit_trail(db, ctx)

    # ── Update farmer_crop last_recommendation ────────────────────────────
    await _update_farmer_crop(db, ctx)

    return ctx


async def _load_context_from_db(db: AsyncSession, farmer_crop_id: str) -> PipelineContext | None:
    """Reconstruct a PipelineContext from the database for an existing farmer_crop row."""
    from app.models import FarmerCrop, CropCanon, Mandi, FarmerProfile
    from app.agents.context import CropInfo, MandiInfo
    import math

    fc = await db.get(FarmerCrop, farmer_crop_id)
    if not fc:
        # Self-healing fallback: if DB was reset/recreated, auto-heal the requested farmer_crop_id
        logger.warning(f"farmer_crop_id {farmer_crop_id} missing from DB — auto-repairing profile")
        try:
            crop_q = await db.execute(select(CropCanon).limit(1))
            crop_row = crop_q.scalars().first()
            crop_id = crop_row.id if crop_row else 1

            new_profile_id = str(uuid.uuid4())
            profile = FarmerProfile(
                id=new_profile_id,
                district="Ujjain",
                state="Madhya Pradesh",
                travel_radius_km=30,
            )
            db.add(profile)

            fc = FarmerCrop(
                id=farmer_crop_id,
                farmer_id=new_profile_id,
                canonical_crop_id=crop_id,
                quantity_quintals=50.0,
            )
            db.add(fc)
            await db.commit()
        except Exception as auto_err:
            logger.warning(f"Auto-repair profile failed: {auto_err}")
            try:
                await db.rollback()
            except Exception:
                pass
            fc = await db.get(FarmerCrop, farmer_crop_id)
            if not fc:
                return None

    ctx = PipelineContext()
    ctx.farmer_crop_id = farmer_crop_id

    # Load crop info
    crop_row = await db.get(CropCanon, fc.canonical_crop_id)
    if crop_row:
        ctx.crop = CropInfo(
            id=crop_row.id,
            canonical_name=crop_row.canonical_name,
            variety=crop_row.variety,
            is_perishable=crop_row.is_perishable,
            shelf_life_days=crop_row.shelf_life_days,
            aliases=crop_row.get_aliases(),
        )

    # Load farmer profile
    if fc.farmer_id:
        profile = await db.get(FarmerProfile, fc.farmer_id)
        if profile:
            ctx.district = profile.district
            ctx.state = profile.state
            ctx.farmer_lat = float(profile.latitude) if profile.latitude else None
            ctx.farmer_lon = float(profile.longitude) if profile.longitude else None
            ctx.travel_radius_km = profile.travel_radius_km
            ctx.transport_cost_per_km = float(getattr(profile, "transport_cost_per_km", 18.0))
            ctx.farmer_profile_id = fc.farmer_id

    ctx.quantity_quintals = float(fc.quantity_quintals or 0)
    ctx.readiness_date = fc.readiness_date
    ctx.home_mandi_id = fc.home_mandi_id

    # Reload mandis in radius
    if ctx.state and ctx.farmer_lat:
        result = await db.execute(
            select(Mandi).where(Mandi.state == ctx.state, Mandi.is_active == True)
        )
        all_mandis = result.scalars().all()
        radius_mandis = []
        for m in all_mandis:
            if m.latitude and m.longitude:
                lat1, lon1 = ctx.farmer_lat, ctx.farmer_lon
                lat2, lon2 = float(m.latitude), float(m.longitude)
                R = 6371
                phi1, phi2 = math.radians(lat1), math.radians(lat2)
                a = math.sin((lat2 - lat1) / 2 * math.pi / 180) ** 2 + \
                    math.cos(phi1) * math.cos(phi2) * math.sin((lon2 - lon1) / 2 * math.pi / 180) ** 2
                dist = 2 * R * math.asin(math.sqrt(max(0, a)))
                if dist <= ctx.travel_radius_km:
                    radius_mandis.append(MandiInfo(
                        id=m.id, name=m.name, state=m.state, district=m.district,
                        latitude=float(m.latitude), longitude=float(m.longitude),
                        distance_km=round(dist, 1),
                    ))
        ctx.mandis_in_radius = sorted(radius_mandis, key=lambda x: x.distance_km or 0)
    elif not ctx.state:
        # Fallback: use all mandis (for session-only queries with no saved profile)
        result = await db.execute(select(Mandi).where(Mandi.is_active == True).limit(10))
        all_mandis = result.scalars().all()
        ctx.mandis_in_radius = [
            MandiInfo(id=m.id, name=m.name, state=m.state, district=m.district,
                      latitude=float(m.latitude or 0), longitude=float(m.longitude or 0), distance_km=0)
            for m in all_mandis
        ]

    return ctx


async def _save_audit_trail(db: AsyncSession, ctx: PipelineContext):
    """Persist all audit trail entries for this pipeline run to the DB."""
    try:
        for step in ctx.audit_trail:
            db.add(AuditTrail(
                farmer_crop_id=ctx.farmer_crop_id,
                session_id=ctx.session_id,
                step_number=step.step_number,
                agent_name=step.agent_name,
                message=step.message,
                technical_detail=step.technical_detail,
                data_tier=step.data_tier,
            ))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"Audit trail save failed: {e}")


async def _update_farmer_crop(db: AsyncSession, ctx: PipelineContext):
    """Update last_recommendation on the farmer_crop row."""
    if not ctx.recommendation:
        return
    try:
        fc = await db.get(FarmerCrop, ctx.farmer_crop_id)
        if fc:
            fc.last_recommendation = ctx.recommendation.recommendation
            fc.last_recommendation_detail = ctx.recommendation.headline
            fc.last_recommendation_at = datetime.utcnow()
            await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"Farmer crop recommendation update failed: {e}")
