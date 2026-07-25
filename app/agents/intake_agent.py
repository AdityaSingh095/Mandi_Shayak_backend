"""
app/agents/intake_agent.py
─────────────────────────────────────────────────────────
Agent 1: Validates farmer input, finds mandis in travel radius,
creates FarmerProfile and FarmerCrop DB rows.
"""

import math
import uuid
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import PipelineContext, MandiInfo
from app.models import FarmerProfile, FarmerCrop, Mandi
from app.schemas import IntakeRequest
from app.config import cfg_int

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two lat/lon points in km."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def run_intake_agent(
    db: AsyncSession, request: IntakeRequest
) -> PipelineContext:
    """
    Validates the intake request, resolves mandis, creates DB records.
    Returns a populated PipelineContext ready for the normalization agent.
    """
    ctx = PipelineContext()
    ctx.district = request.district.strip()
    ctx.state = request.state.strip()
    ctx.travel_radius_km = min(request.travel_radius_km, 150)
    ctx.quantity_quintals = request.quantity_quintals or 0.0
    ctx.transport_cost_per_km = request.transport_cost_per_km
    ctx.readiness_date = request.readiness_date

    # ── Step 1: Find mandis in the same state ──────────────────────────────
    result = await db.execute(
        select(Mandi).where(
            Mandi.state == ctx.state,
            Mandi.is_active == True,
        )
    )
    all_state_mandis = result.scalars().all()

    # ── Step 2: Find home mandi (same district, closest) ──────────────────
    same_district = [m for m in all_state_mandis if m.district.lower() == ctx.district.lower()]
    if same_district:
        home = same_district[0]
        ctx.farmer_lat = float(home.latitude or 0)
        ctx.farmer_lon = float(home.longitude or 0)
        ctx.home_mandi_id = home.id
    elif all_state_mandis:
        home = all_state_mandis[0]
        ctx.farmer_lat = float(home.latitude or 0)
        ctx.farmer_lon = float(home.longitude or 0)
        ctx.home_mandi_id = home.id
    else:
        ctx.farmer_lat = 22.0
        ctx.farmer_lon = 77.0
        ctx.home_mandi_id = None

    # ── Step 3: Filter mandis within travel radius ─────────────────────────
    radius_mandis: list[MandiInfo] = []
    for m in all_state_mandis:
        if m.latitude and m.longitude:
            dist = _haversine_km(ctx.farmer_lat, ctx.farmer_lon, float(m.latitude), float(m.longitude))
            if dist <= ctx.travel_radius_km:
                radius_mandis.append(MandiInfo(
                    id=m.id, name=m.name, state=m.state, district=m.district,
                    latitude=float(m.latitude), longitude=float(m.longitude),
                    distance_km=round(dist, 1),
                ))

    # Guarantee at least 3 mandis even if radius is tight
    if len(radius_mandis) < 3:
        for m in all_state_mandis:
            if m.id not in {mi.id for mi in radius_mandis} and m.latitude and m.longitude:
                dist = _haversine_km(ctx.farmer_lat, ctx.farmer_lon, float(m.latitude), float(m.longitude))
                radius_mandis.append(MandiInfo(
                    id=m.id, name=m.name, state=m.state, district=m.district,
                    latitude=float(m.latitude), longitude=float(m.longitude),
                    distance_km=round(dist, 1),
                ))
                if len(radius_mandis) >= 5:
                    break

    ctx.mandis_in_radius = sorted(radius_mandis, key=lambda x: x.distance_km or 0)

    # ── Step 4: Create FarmerProfile + FarmerCrop rows ────────────────────
    farmer_profile = None
    if request.save_profile and request.phone_or_contact:
        farmer_profile = FarmerProfile(
            id=str(uuid.uuid4()),
            phone_or_contact=request.phone_or_contact,
            district=ctx.district,
            state=ctx.state,
            latitude=ctx.farmer_lat,
            longitude=ctx.farmer_lon,
            travel_radius_km=ctx.travel_radius_km,
            transport_cost_per_km=ctx.transport_cost_per_km,
            notification_channel=request.notification_channel,
            consent_given=False,  # Must be explicitly confirmed via /profile/save
        )
        db.add(farmer_profile)
        ctx.farmer_profile_id = farmer_profile.id

    farmer_crop = FarmerCrop(
        id=ctx.farmer_crop_id,
        farmer_id=farmer_profile.id if farmer_profile else None,
        canonical_crop_id=1,  # placeholder; updated after normalization
        home_mandi_id=ctx.home_mandi_id,
        quantity_quintals=ctx.quantity_quintals,
        readiness_date=ctx.readiness_date,
    )
    db.add(farmer_crop)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"DB commit failed in intake agent: {e}")

    mandi_names = ", ".join(m.name for m in ctx.mandis_in_radius[:5])
    ctx.append_audit(
        agent_name="INTAKE",
        message=(
            f"Profile received for {ctx.district}, {ctx.state}. "
            f"Travel radius: {ctx.travel_radius_km}km. "
            f"Found {len(ctx.mandis_in_radius)} mandis in radius."
        ),
        technical_detail=f"Mandis: {mandi_names}. Home mandi ID: {ctx.home_mandi_id}.",
    )

    return ctx
