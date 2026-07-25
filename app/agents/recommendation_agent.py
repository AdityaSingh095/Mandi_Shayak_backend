"""
app/agents/recommendation_agent.py
─────────────────────────────────────────────────────────
Agent 6: Applies priority-ordered rule table to produce
SELL_NOW | SELL_LOCAL | HOLD | TRAVEL | CONSIDER_TRAVEL |
MONITOR | INSUFFICIENT_DATA recommendations.
Zero ML — purely deterministic.
"""

import logging
from datetime import date

from app.agents.context import PipelineContext, RecommendationData, MandiInfo
from app.config import cfg_float

logger = logging.getLogger(__name__)


def _get_local_trend(ctx: PipelineContext):
    return ctx.trend_data.get(ctx.home_mandi_id)


def _get_best_arbitrage(ctx: PipelineContext):
    """Returns best worthwhile arbitrage result (excluding local mandi)."""
    alts = [r for r in ctx.arbitrage_results if r.mandi_id != ctx.home_mandi_id]
    if not alts:
        return None
    return alts[0]  # Already sorted by net_gain descending


def _projected_gain(ctx: PipelineContext, days: int = 4) -> float | None:
    """
    Simple linear extrapolation of rising trend over N days.
    Returns projected extra ₹ for full quantity.
    Clearly labeled as not a guarantee.
    """
    local_trend = _get_local_trend(ctx)
    if not local_trend or not local_trend.ma7 or not local_trend.percent_change:
        return None
    if ctx.quantity_quintals <= 0:
        return None

    # Daily rate from percent change over 7 days
    daily_pct = local_trend.percent_change / 7.0 / 100.0
    current_price = local_trend.ma7
    projected_price = current_price * ((1 + daily_pct) ** days)
    extra_per_qtl = projected_price - current_price
    return round(extra_per_qtl * ctx.quantity_quintals, 2)


async def run_recommendation_agent(ctx: PipelineContext) -> PipelineContext:
    """
    Applies rule table R1–R8. First matching rule fires.
    Mutates ctx.recommendation.
    """
    strong_travel_threshold = cfg_float("arbitrage.strong_travel_gain_inr", 1000.0)
    min_worthwhile = cfg_float("arbitrage.min_worthwhile_gain_inr", 500.0)

    local_trend = _get_local_trend(ctx)
    best_arb = _get_best_arbitrage(ctx)

    perishability_warning = False
    if ctx.crop and ctx.crop.is_perishable and ctx.readiness_date:
        days_left = (ctx.readiness_date - date.today()).days
        if days_left <= (ctx.crop.shelf_life_days or 5):
            perishability_warning = True

    rec: RecommendationData | None = None

    # ── R1: Insufficient Data ─────────────────────────────────────────────
    all_insufficient = all(
        t.trend == "INSUFFICIENT_DATA"
        for t in ctx.trend_data.values()
    ) or not ctx.trend_data

    if all_insufficient:
        rec = RecommendationData(
            recommendation="INSUFFICIENT_DATA",
            headline="Not enough price data yet.",
            full_explanation=(
                "We don't have enough recent price records to make a recommendation. "
                "Data is being collected. Please check back tomorrow or register for "
                "automatic monitoring — you'll be notified when data is available."
            ),
            confidence="LOW",
        )

    # ── R2: Falling price — SELL NOW ─────────────────────────────────────
    elif (
        local_trend
        and local_trend.trend == "FALLING"
        and local_trend.percent_change is not None
        and local_trend.percent_change <= -5.0
        and local_trend.confidence in ("HIGH", "MEDIUM")
    ):
        price = local_trend.ma7 or 0
        rec = RecommendationData(
            recommendation="SELL_NOW",
            headline=f"⚡ Sell Now — Prices falling sharply ({local_trend.percent_change:.1f}% / 7 days)",
            full_explanation=(
                f"Prices at your local mandi are falling sharply "
                f"({local_trend.percent_change:.1f}% over the last 7 days). "
                f"Current price: ₹{price:.0f}/quintal. "
                f"Immediate sale minimizes further loss."
            ),
            confidence=local_trend.confidence,
            perishability_warning=perishability_warning,
        )

    # ── R3: Strong arbitrage — TRAVEL ────────────────────────────────────
    elif (
        best_arb
        and best_arb.is_worthwhile
        and best_arb.net_gain_over_local >= strong_travel_threshold
        and best_arb.data_tier != "DEMO"  # Never recommend travel on demo data
        and not best_arb.time_risk
    ):
        best_mandi = next(
            (m for m in ctx.mandis_in_radius if m.id == best_arb.mandi_id), None
        )
        rec = RecommendationData(
            recommendation="TRAVEL",
            headline=f"🚛 Travel to {best_arb.mandi_name} — Net extra: ₹{best_arb.net_gain_over_local:.0f}",
            full_explanation=(
                f"Traveling to {best_arb.mandi_name} ({best_arb.distance_km}km away) "
                f"yields ₹{best_arb.net_gain_over_local:.0f} more than selling locally "
                f"after deducting ₹{best_arb.transport_cost:.0f} transport cost. "
                f"Price there: ₹{best_arb.modal_price:.0f}/qtl vs local ₹{local_trend.ma7:.0f if local_trend and local_trend.ma7 else 0}/qtl."
            ),
            primary_mandi=best_mandi,
            confidence=local_trend.confidence if local_trend else "MEDIUM",
            perishability_warning=perishability_warning,
        )

    # ── R4: Rising trend — HOLD ──────────────────────────────────────────
    elif (
        local_trend
        and local_trend.trend == "RISING"
        and local_trend.percent_change is not None
        and local_trend.percent_change >= 2.5
        and local_trend.confidence in ("HIGH", "MEDIUM")
        and not perishability_warning
    ):
        gain = _projected_gain(ctx, days=4)
        rec = RecommendationData(
            recommendation="HOLD",
            headline=f"⏳ Hold 3–5 Days — Prices rising (+{local_trend.percent_change:.1f}% / 7 days)",
            full_explanation=(
                f"Prices at your local mandi are rising "
                f"(+{local_trend.percent_change:.1f}% over 7 days). "
                + (f"If the trend continues, holding for 4 days could yield "
                   f"~₹{gain:.0f} more for your quantity. " if gain else "")
                + "This projection is based on current trend only — not a guarantee."
            ),
            projected_extra_if_hold=gain,
            projected_hold_days=4,
            confidence=local_trend.confidence,
            perishability_warning=perishability_warning,
        )

    # ── R5: Stable + no worthwhile arbitrage — SELL LOCAL ────────────────
    elif (
        local_trend
        and local_trend.trend == "STABLE"
        and (not best_arb or not best_arb.is_worthwhile)
    ):
        price = local_trend.ma7 or 0
        rec = RecommendationData(
            recommendation="SELL_LOCAL",
            headline=f"✅ Sell Now (Local) — Stable price at ₹{price:.0f}/qtl",
            full_explanation=(
                f"Prices are stable at ₹{price:.0f}/quintal at your local mandi. "
                f"No nearby mandi offers enough extra return after transport costs. "
                f"Selling locally is the best option."
            ),
            confidence=local_trend.confidence,
            perishability_warning=perishability_warning,
        )

    # ── R6: Moderate arbitrage — CONSIDER TRAVEL ─────────────────────────
    elif (
        best_arb
        and best_arb.is_worthwhile
        and min_worthwhile <= best_arb.net_gain_over_local < strong_travel_threshold
        and best_arb.data_tier != "DEMO"
    ):
        rec = RecommendationData(
            recommendation="CONSIDER_TRAVEL",
            headline=f"🔵 Consider Travel to {best_arb.mandi_name} — ₹{best_arb.net_gain_over_local:.0f} extra",
            full_explanation=(
                f"Modest extra return of ₹{best_arb.net_gain_over_local:.0f} available at "
                f"{best_arb.mandi_name} ({best_arb.distance_km}km). "
                f"Worth considering if you are planning a trip in that direction."
            ),
            primary_mandi=next((m for m in ctx.mandis_in_radius if m.id == best_arb.mandi_id), None),
            confidence=local_trend.confidence if local_trend else "LOW",
            perishability_warning=perishability_warning,
        )

    # ── R7: Volatile market — MONITOR ────────────────────────────────────
    elif local_trend and local_trend.is_volatile:
        vol_pct = round((local_trend.volatility_ratio or 0) * 100, 1)
        rec = RecommendationData(
            recommendation="MONITOR",
            headline=f"📊 Monitor Daily — Market is volatile (±{vol_pct}% fluctuation)",
            full_explanation=(
                f"Prices are fluctuating significantly day to day (±{vol_pct}%). "
                f"Selling on a high day is recommended. "
                f"Check back tomorrow before deciding."
            ),
            confidence=local_trend.confidence,
            perishability_warning=perishability_warning,
        )

    # ── Fallback ─────────────────────────────────────────────────────────
    else:
        price = local_trend.ma7 if local_trend and local_trend.ma7 else 0
        rec = RecommendationData(
            recommendation="SELL_LOCAL",
            headline=f"✅ Sell at Local Mandi — ₹{price:.0f}/qtl",
            full_explanation=(
                "Based on available data, selling at your local mandi is the recommended action."
            ),
            confidence="LOW",
            perishability_warning=perishability_warning,
        )

    # ── R8: Perishability override note ──────────────────────────────────
    if perishability_warning and rec.recommendation == "HOLD":
        rec.recommendation = "SELL_LOCAL"
        rec.headline = "⚠️ Sell Now — Crop near harvest/expiry date"
        rec.full_explanation = (
            "Your crop is perishable and the harvest/readiness date is approaching. "
            "Prioritize early sale over maximum price to avoid spoilage loss. "
            + rec.full_explanation
        )

    # ── Demo data travel suppression ─────────────────────────────────────
    if ctx.overall_data_tier == "DEMO" and rec.recommendation in ("TRAVEL", "CONSIDER_TRAVEL"):
        rec.recommendation = "SELL_LOCAL"
        rec.headline = "⚠️ Live data required for travel recommendations"
        rec.full_explanation = (
            "Travel recommendations are suppressed when using demo data. "
            "Register a free API key at data.gov.in for real-time arbitrage analysis."
        )
        rec.primary_mandi = None

    ctx.recommendation = rec

    ctx.append_audit(
        agent_name="RECOMMENDATION",
        message=f"Rule matched → {rec.recommendation}. {rec.headline}",
        technical_detail=(
            f"Local trend: {local_trend.trend if local_trend else 'N/A'} "
            f"({local_trend.percent_change:.1f}% change)" if local_trend and local_trend.percent_change else ""
            + f" | Best arb: {best_arb.mandi_name} +₹{best_arb.net_gain_over_local:.0f}" if best_arb else ""
            + f" | Perishability warning: {perishability_warning}."
        ),
        data_tier=ctx.overall_data_tier,
    )
    return ctx
