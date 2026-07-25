"""
app/agents/trend_agent.py
─────────────────────────────────────────────────────────
Agent 4: Deterministic trend detection.
MA7 vs MA30 crossover + standard deviation volatility.
No ML, no external calls — pure Python arithmetic.
"""

import logging
import math
from datetime import date, timedelta
from typing import Optional

from app.agents.context import PipelineContext, TrendData
from app.config import cfg_float, cfg_int

logger = logging.getLogger(__name__)


def _interpolate_gaps(prices: list[tuple[date, float]], max_gap: int) -> list[tuple[date, float]]:
    """
    Linear interpolation for small gaps in price series.
    Only fills gaps <= max_gap consecutive days.
    Does NOT modify original data — returns a new list.
    """
    if len(prices) < 2:
        return prices

    filled = [prices[0]]
    for i in range(1, len(prices)):
        prev_date, prev_price = filled[-1]
        curr_date, curr_price = prices[i]
        gap = (curr_date - prev_date).days - 1

        if 0 < gap <= max_gap:
            # Interpolate missing days
            for g in range(1, gap + 1):
                interp_date = prev_date + timedelta(days=g)
                t = g / (gap + 1)
                interp_price = prev_price + t * (curr_price - prev_price)
                filled.append((interp_date, round(interp_price, 2)))

        filled.append((curr_date, curr_price))
    return filled


def _compute_trend(prices: list[tuple[date, float]]) -> TrendData | None:
    """
    Compute MA7, MA30, percent change, volatility for a price series.
    Returns None if insufficient data.
    """
    rising_threshold = cfg_float("trend.rising_threshold_pct", 2.5)
    falling_threshold = cfg_float("trend.falling_threshold_pct", -2.5)
    vol_threshold = cfg_float("trend.volatility_threshold_ratio", 0.05)
    min_days = cfg_int("trend.min_days_for_analysis", 7)
    max_gap = cfg_int("trend.gap_interpolation_max_days", 2)

    return_insufficient = TrendData(
        mandi_id=0, mandi_name="",
        trend="INSUFFICIENT_DATA",
        days_of_data=len(prices),
    )

    if len(prices) < min_days:
        return return_insufficient

    # Count gaps before interpolation
    gap_days = 0
    for i in range(1, len(prices)):
        gap = (prices[i][0] - prices[i - 1][0]).days - 1
        if gap > 0:
            gap_days += gap

    # Interpolate small gaps
    prices = _interpolate_gaps(prices, max_gap)
    all_modals = [p[1] for p in prices]
    last_7 = all_modals[-7:]
    last_30 = all_modals[-30:] if len(all_modals) >= 30 else all_modals

    ma7 = sum(last_7) / len(last_7)
    ma30 = sum(last_30) / len(last_30)
    percent_change = ((ma7 - ma30) / ma30) * 100 if ma30 != 0 else 0.0

    # Volatility (std dev of last 7 days)
    mean7 = ma7
    variance = sum((p - mean7) ** 2 for p in last_7) / len(last_7)
    std_dev = math.sqrt(variance)
    vol_ratio = std_dev / ma7 if ma7 != 0 else 0.0
    is_volatile = vol_ratio > vol_threshold

    # Trend classification
    if percent_change >= rising_threshold:
        trend = "RISING"
    elif percent_change <= falling_threshold:
        trend = "FALLING"
    else:
        trend = "STABLE"

    # Momentum
    momentum = None
    if len(all_modals) >= 3:
        last_2_change = ((all_modals[-1] - all_modals[-3]) / all_modals[-3]) * 100
        if trend == "RISING" and last_2_change > 1.5:
            momentum = "ACCELERATING"
        elif trend == "RISING" and last_2_change < -1.5:
            momentum = "DECELERATING"
        else:
            momentum = "STABLE_RECENT"

    # Confidence
    n = len(all_modals)
    if n >= 25 and gap_days <= 1:
        confidence = "HIGH"
    elif n >= 15 and gap_days <= 3:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return TrendData(
        mandi_id=0,
        mandi_name="",
        trend=trend,
        ma7=round(ma7, 2),
        ma30=round(ma30, 2),
        percent_change=round(percent_change, 2),
        is_volatile=is_volatile,
        volatility_ratio=round(vol_ratio, 4),
        confidence=confidence,
        days_of_data=len(all_modals),
        gap_days=gap_days,
        momentum=momentum,
    )


async def run_trend_agent(ctx: PipelineContext) -> PipelineContext:
    """
    Computes trend for each mandi's price series.
    Pure computation — no DB or external calls needed.
    """
    for mandi_id, packet in ctx.price_data.items():
        mandi_name = packet.mandi_name

        # Convert records to sorted (date, modal_price) tuples
        series: list[tuple[date, float]] = []
        for r in packet.records:
            d = r.get("arrival_date")
            p = r.get("modal_price")
            if d is None or p is None:
                continue
            if isinstance(d, str):
                try:
                    from datetime import datetime
                    d = datetime.strptime(d, "%d/%m/%Y").date()
                except Exception:
                    continue
            if isinstance(d, date) and p:
                series.append((d, float(p)))

        series.sort(key=lambda x: x[0])

        trend = _compute_trend(series)
        if trend:
            trend.mandi_id = mandi_id
            trend.mandi_name = mandi_name
        else:
            trend = TrendData(mandi_id=mandi_id, mandi_name=mandi_name, trend="INSUFFICIENT_DATA")

        ctx.trend_data[mandi_id] = trend

        ctx.append_audit(
            agent_name="TREND_DETECTION",
            message=(
                f"{mandi_name}: Trend is {trend.trend}. "
                + (f"MA7=₹{trend.ma7:.0f}, MA30=₹{trend.ma30:.0f}, Change={trend.percent_change:.1f}%." if trend.ma7 else "Insufficient data.")
                + (f" Market is {'volatile' if trend.is_volatile else 'stable'}." if trend.ma7 else "")
            ),
            technical_detail=(
                f"MA7={trend.ma7}, MA30={trend.ma30}, %change={trend.percent_change}, "
                f"StdDev ratio={trend.volatility_ratio}, confidence={trend.confidence}, "
                f"days={trend.days_of_data}, gaps={trend.gap_days}, momentum={trend.momentum}."
            ) if trend.ma7 else f"Days of data: {trend.days_of_data} (min required: {cfg_int('trend.min_days_for_analysis', 7)}).",
            data_tier=packet.data_tier,
        )

    return ctx
