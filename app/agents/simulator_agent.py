"""
app/agents/simulator_agent.py
─────────────────────────────────────────────────────────
Harvest Sell Window & Storage Shrinkage Simulator Agent.
Calculates day-by-day net revenue over 14 days, accounting for:
  - Moisture Shrinkage Loss (% weight loss per day)
  - Daily Storage Fees (₹/quintal/day)
  - Projected Price Trend (Moving Average Momentum)
100% deterministic, zero external paid APIs, < 5ms execution.
"""

from typing import List, Dict, Any
from pydantic import BaseModel


class DailySimulationPoint(BaseModel):
    day: int
    date_offset_label: str
    projected_price: float
    effective_quantity_quintals: float
    storage_shrinkage_loss_quintals: float
    gross_revenue: float
    cumulative_storage_cost: float
    net_revenue: float
    net_gain_vs_today: float


class SimulationResult(BaseModel):
    crop_name: str
    initial_quantity_quintals: float
    current_price: float
    daily_shrinkage_rate_pct: float
    storage_fee_per_qtl_day: float
    optimal_sell_day: int
    optimal_sell_label: str
    optimal_net_revenue: float
    optimal_gain_vs_today: float
    recommendation_summary: str
    timeline: List[DailySimulationPoint]


# Crop-specific moisture shrinkage rates (% weight loss per week)
SHRINKAGE_RATES_PER_WEEK = {
    "onion": 3.0,
    "pyaaz": 3.0,
    "tomato": 7.0,
    "tamatar": 7.0,
    "potato": 1.0,
    "aalu": 1.0,
    "paddy": 1.5,
    "dhan": 1.5,
    "rice": 1.5,
    "wheat": 0.5,
    "gehun": 0.5,
    "mustard": 0.5,
    "sarson": 0.5,
    "soybean": 0.6,
    "gram": 0.5,
    "chana": 0.5,
}


def run_sell_window_simulation(
    crop_name: str,
    quantity_quintals: float,
    current_price: float,
    trend_momentum_pct_per_day: float = 0.5,
    storage_fee_per_qtl_day: float = 1.0,
    projection_days: int = 14
) -> SimulationResult:
    """
    Computes holding cost vs storage shrinkage over N days.
    Identifies the exact day that maximizes net profit after storage.
    """
    crop_lower = crop_name.lower().strip()
    weekly_shrinkage = 1.0
    for k, v in SHRINKAGE_RATES_PER_WEEK.items():
        if k in crop_lower:
            weekly_shrinkage = v
            break
            
    daily_shrinkage_pct = weekly_shrinkage / 7.0
    daily_shrinkage_rate = daily_shrinkage_pct / 100.0
    
    timeline: List[DailySimulationPoint] = []
    
    # Baseline today (Day 0)
    today_net_revenue = quantity_quintals * current_price
    
    optimal_day = 0
    max_net_revenue = today_net_revenue
    
    for day in range(0, projection_days + 1):
        if day == 0:
            proj_price = current_price
        else:
            # Price trend trajectory projection with realistic diminishing momentum
            price_factor = 1.0 + ((trend_momentum_pct_per_day / 100.0) * day * (1.0 - 0.03 * day))
            proj_price = round(current_price * price_factor, 2)
            
        eff_qty = round(quantity_quintals * ((1.0 - daily_shrinkage_rate) ** day), 2)
        shrinkage_loss = round(quantity_quintals - eff_qty, 2)
        gross_rev = round(eff_qty * proj_price, 2)
        cum_storage_cost = round(quantity_quintals * storage_fee_per_qtl_day * day, 2)
        net_rev = round(gross_rev - cum_storage_cost, 2)
        net_gain = round(net_rev - today_net_revenue, 2)
        
        if net_rev > max_net_revenue:
            max_net_revenue = net_rev
            optimal_day = day
            
        timeline.append(DailySimulationPoint(
            day=day,
            date_offset_label="Today" if day == 0 else f"+{day} Days",
            projected_price=proj_price,
            effective_quantity_quintals=eff_qty,
            storage_shrinkage_loss_quintals=shrinkage_loss,
            gross_revenue=gross_rev,
            cumulative_storage_cost=cum_storage_cost,
            net_revenue=net_rev,
            net_gain_vs_today=net_gain,
        ))
        
    optimal_gain = round(max_net_revenue - today_net_revenue, 2)
    
    if optimal_day == 0 or optimal_gain <= 0:
        summary = f"Sell Today. Holding {crop_name} in storage will lose money due to weight shrinkage and storage fees."
        opt_label = "Sell Today (Day 0)"
    else:
        summary = f"Optimal Sell Target: Day {optimal_day}. Holding for {optimal_day} days yields an estimated +₹{optimal_gain:,.2f} net gain after storage shrinkage."
        opt_label = f"Day {optimal_day} (+{optimal_day} Days)"
        
    return SimulationResult(
        crop_name=crop_name,
        initial_quantity_quintals=quantity_quintals,
        current_price=current_price,
        daily_shrinkage_rate_pct=round(daily_shrinkage_pct, 3),
        storage_fee_per_qtl_day=storage_fee_per_qtl_day,
        optimal_sell_day=optimal_day,
        optimal_sell_label=opt_label,
        optimal_net_revenue=max_net_revenue,
        optimal_gain_vs_today=optimal_gain,
        recommendation_summary=summary,
        timeline=timeline,
    )
