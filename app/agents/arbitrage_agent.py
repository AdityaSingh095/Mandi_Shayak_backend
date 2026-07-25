"""
app/agents/arbitrage_agent.py
─────────────────────────────────────────────────────────
Agent 5: Cross-mandi arbitrage evaluation.
Haversine distance + transport cost subtraction + perishability constraint.
Pure deterministic arithmetic — no ML, no DB calls needed.
"""

import math
import logging
from datetime import date

from app.agents.context import PipelineContext, ArbitrageData, MandiInfo
from app.config import cfg_float

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _latest_modal_price(packet) -> float | None:
    """Get the most recent modal price from a price data packet."""
    records = packet.records
    if not records:
        return None
    sorted_records = sorted(
        records,
        key=lambda r: r.get("arrival_date", date.min) if isinstance(r.get("arrival_date"), date) else date.min,
        reverse=True
    )
    for r in sorted_records:
        p = r.get("modal_price")
        if p:
            return float(p)
    return None


def _check_perishability_time_risk(
    ctx: PipelineContext, mandi: MandiInfo
) -> bool:
    """
    Returns True if traveling to this mandi poses spoilage risk
    given the crop's readiness_date and travel distance.
    """
    if not ctx.crop or not ctx.crop.is_perishable:
        return False
    if not ctx.readiness_date:
        return False

    days_until_ready = (ctx.readiness_date - date.today()).days
    if days_until_ready < 0:
        return False  # Already ready — time risk depends on distance now

    if mandi.distance_km:
        # Estimate round-trip travel + market time in days at 80km/h
        est_trip_days = (mandi.distance_km / 80) * 2
        if est_trip_days > days_until_ready:
            return True
    return False


async def run_arbitrage_agent(ctx: PipelineContext) -> PipelineContext:
    """
    Computes net gain of selling at each alternate mandi vs local mandi.
    Populates ctx.arbitrage_results sorted by net_gain_over_local descending.
    """
    if not ctx.price_data or not ctx.home_mandi_id:
        ctx.append_audit(
            agent_name="ARBITRAGE",
            message="Skipping arbitrage — no price data or home mandi not set.",
        )
        return ctx

    min_worthwhile = cfg_float("arbitrage.min_worthwhile_gain_inr", 500.0)
    qty = ctx.quantity_quintals or 1.0
    cost_per_km = ctx.transport_cost_per_km

    # ── Get local mandi price ─────────────────────────────────────────────
    local_packet = ctx.price_data.get(ctx.home_mandi_id)
    if not local_packet:
        # Use first available mandi as local
        ctx.home_mandi_id = next(iter(ctx.price_data))
        local_packet = ctx.price_data[ctx.home_mandi_id]

    local_price = _latest_modal_price(local_packet)
    if not local_price:
        ctx.append_audit(
            agent_name="ARBITRAGE",
            message="Could not determine local mandi price — arbitrage skipped.",
        )
        return ctx

    local_revenue = local_price * qty
    results: list[ArbitrageData] = []

    for mandi in ctx.mandis_in_radius:
        packet = ctx.price_data.get(mandi.id)
        if not packet:
            continue

        modal_price = _latest_modal_price(packet)
        if not modal_price or modal_price <= 0:
            continue

        # Distance
        if mandi.id == ctx.home_mandi_id:
            distance_km = 0.0
        elif ctx.farmer_lat and ctx.farmer_lon and mandi.latitude and mandi.longitude:
            distance_km = _haversine_km(
                ctx.farmer_lat, ctx.farmer_lon,
                mandi.latitude, mandi.longitude
            )
        else:
            distance_km = mandi.distance_km or 50.0

        round_trip_cost = distance_km * 2 * cost_per_km
        gross_revenue = modal_price * qty
        net_revenue = gross_revenue - round_trip_cost
        net_gain = net_revenue - local_revenue
        per_qtl_gain = net_gain / qty if qty > 0 else 0

        trend = ctx.trend_data.get(mandi.id)
        trend_str = trend.trend if trend else "UNKNOWN"
        time_risk = _check_perishability_time_risk(ctx, mandi)

        results.append(ArbitrageData(
            mandi_id=mandi.id,
            mandi_name=mandi.name,
            distance_km=round(distance_km, 1),
            modal_price=modal_price,
            gross_revenue=round(gross_revenue, 2),
            transport_cost=round(round_trip_cost, 2),
            net_revenue=round(net_revenue, 2),
            net_gain_over_local=round(net_gain, 2),
            per_quintal_gain=round(per_qtl_gain, 2),
            is_worthwhile=net_gain >= min_worthwhile,
            trend=trend_str,
            data_tier=packet.data_tier,
            time_risk=time_risk,
        ))

    results.sort(key=lambda x: x.net_gain_over_local, reverse=True)
    ctx.arbitrage_results = results

    best = results[0] if results else None
    local_mandi_name = local_packet.mandi_name

    ctx.append_audit(
        agent_name="ARBITRAGE",
        message=(
            f"Local mandi ({local_mandi_name}): ₹{local_price:.0f}/qtl. "
            + (
                f"Best alternate: {best.mandi_name} (₹{best.modal_price:.0f}/qtl, "
                f"net gain ₹{best.net_gain_over_local:.0f} after transport ₹{best.transport_cost:.0f}). "
                f"{'WORTHWHILE.' if best.is_worthwhile else 'Not worthwhile after transport.'}"
                if best and best.mandi_id != ctx.home_mandi_id else "No better alternate mandi found."
            )
        ),
        technical_detail=(
            f"Qty={qty}qtl, cost/km=₹{cost_per_km}. "
            f"Local revenue=₹{local_revenue:.0f}. "
            + (f"Best: {best.mandi_name}, dist={best.distance_km}km, "
               f"gross=₹{best.gross_revenue:.0f}, transport=₹{best.transport_cost:.0f}, "
               f"net_gain=₹{best.net_gain_over_local:.0f}, time_risk={best.time_risk}."
               if best else "No alternates available.")
        ),
        data_tier=ctx.overall_data_tier,
    )

    return ctx
