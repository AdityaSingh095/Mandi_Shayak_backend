"""
app/agents/report_agent.py
─────────────────────────────────────────────────────────
Detailed Market Intelligence Advisory Report Generator.
Generates comprehensive report with executive summary, arbitrage financial table,
storage shrinkage analysis, moving average trendlines, and audit steps.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import run_full_pipeline
from app.agents.simulator_agent import run_sell_window_simulation, SimulationResult


class ArbitrageRowReport(BaseModel):
    mandi_name: str
    distance_km: float
    modal_price: float
    gross_revenue: float
    transport_cost: float
    net_revenue: float
    net_gain_over_local: float


class AuditStepReport(BaseModel):
    step_number: int
    agent_name: str
    message: str
    technical_detail: Optional[str] = None


class MarketAdvisoryReport(BaseModel):
    farmer_crop_id: str
    generated_at: str
    crop_name: str
    variety: Optional[str] = None
    local_mandi_name: str
    district: str
    state: str
    quantity_quintals: float
    action_recommendation: str
    headline: str
    explanation: str
    best_mandi_name: Optional[str] = None
    best_mandi_distance_km: Optional[float] = None
    expected_extra_profit_inr: float
    data_tier: str
    arbitrage_table: List[ArbitrageRowReport]
    simulation: SimulationResult
    audit_trail: List[AuditStepReport]
    markdown_report: str


async def generate_market_advisory_report(
    db: AsyncSession, farmer_crop_id: str
) -> MarketAdvisoryReport:
    """
    Runs the pipeline & simulation to construct a complete Market Intelligence Advisory Report.
    """
    from datetime import datetime
    
    ctx = await run_full_pipeline(db, farmer_crop_id)
    
    local_mandi = ctx.home_mandi()
    local_name = local_mandi.name if local_mandi else "Local Mandi"
    crop_name = ctx.crop.canonical_name if ctx.crop else "Crop"
    variety = ctx.crop.variety if ctx.crop else None
    
    # Run harvest sell window simulation
    local_price = 2400.0
    if ctx.arbitrage_results:
        local_price = ctx.arbitrage_results[-1].modal_price or 2400.0
        
    sim_res = run_sell_window_simulation(
        crop_name=crop_name,
        quantity_quintals=ctx.quantity_quintals or 50.0,
        current_price=local_price,
    )
    
    arbitrage_rows = [
        ArbitrageRowReport(
            mandi_name=r.mandi_name,
            distance_km=r.distance_km,
            modal_price=r.modal_price,
            gross_revenue=r.gross_revenue,
            transport_cost=r.transport_cost,
            net_revenue=r.net_revenue,
            net_gain_over_local=r.net_gain_over_local,
        )
        for r in ctx.arbitrage_results
    ]
    
    audit_rows = [
        AuditStepReport(
            step_number=a.step_number,
            agent_name=a.agent_name,
            message=a.message,
            technical_detail=a.technical_detail,
        )
        for a in ctx.audit_trail
    ]
    
    best_mandi = ctx.recommendation.primary_mandi if ctx.recommendation else None
    best_name = best_mandi.name if best_mandi else None
    best_dist = best_mandi.distance_km if best_mandi else None
    extra_profit = ctx.recommendation.extra_profit_inr if ctx.recommendation else 0.0
    
    rec_action = ctx.recommendation.recommendation if ctx.recommendation else "SELL_NOW"
    headline = ctx.recommendation.headline if ctx.recommendation else "Sell locally at current market rates."
    explanation = ctx.recommendation.full_explanation if ctx.recommendation else "Market analysis completed."
    
    target_mandi_str = ""
    if best_name:
        target_mandi_str = f"**Target Mandi:** {best_name} ({best_dist} km away)  \n**Expected Net Gain:** +₹{extra_profit:,.2f}"

    # Generate Markdown export
    md = f"""# Mandi Sahayak — Market Intelligence Advisory Report

**Report ID:** `{farmer_crop_id}`  
**Generated:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`  
**Crop:** {crop_name} {f'({variety})' if variety else ''}  
**Quantity:** {ctx.quantity_quintals} Quintals  
**Location:** {ctx.district}, {ctx.state}  
**Data Freshness Tier:** `{ctx.overall_data_tier}`  

---

## 1. Executive Recommendation

### **Action:** `{rec_action}`
> **{headline}**
> 
> {explanation}

{target_mandi_str}

---

## 2. Market Arbitrage Comparison

| Mandi Name | Distance (km) | Modal Price (₹/qtl) | Gross Revenue (₹) | Transport Cost (₹) | Net Revenue (₹) | Net Gain (₹) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in arbitrage_rows:
        md += f"| {r.mandi_name} | {r.distance_km} | ₹{r.modal_price:,.2f} | ₹{r.gross_revenue:,.2f} | -₹{r.transport_cost:,.2f} | **₹{r.net_revenue:,.2f}** | {'+₹' + f'{r.net_gain_over_local:,.2f}' if r.net_gain_over_local > 0 else 'Baseline'} |\n"

    md += f"""
---

## 3. Harvest Sell Window & Storage Shrinkage Analysis

- **Daily Weight Loss Rate:** {sim_res.daily_shrinkage_rate_pct}% / day
- **Storage Fee:** ₹{sim_res.storage_fee_per_qtl_day} / qtl / day
- **Optimal Target:** {sim_res.optimal_sell_label}
- **{sim_res.recommendation_summary}**

---

## 4. Agent Pipeline Audit Trail

"""
    for a in audit_rows:
        md += f"- **Step {a.step_number} [{a.agent_name}]:** {a.message}\n"

    return MarketAdvisoryReport(
        farmer_crop_id=farmer_crop_id,
        generated_at=datetime.utcnow().isoformat(),
        crop_name=crop_name,
        variety=variety,
        local_mandi_name=local_name,
        district=ctx.district or "Ujjain",
        state=ctx.state or "Madhya Pradesh",
        quantity_quintals=ctx.quantity_quintals or 50.0,
        action_recommendation=rec_action,
        headline=headline,
        explanation=explanation,
        best_mandi_name=best_name,
        best_mandi_distance_km=best_dist,
        expected_extra_profit_inr=extra_profit,
        data_tier=ctx.overall_data_tier,
        arbitrage_table=arbitrage_rows,
        simulation=sim_res,
        audit_trail=audit_rows,
        markdown_report=md,
    )
