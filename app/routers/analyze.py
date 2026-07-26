"""
app/routers/analyze.py — POST /api/analyze
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    AnalyzeRequest, AnalyzeResponse, RecommendationResult,
    TrendResult, ArbitrageResult, MandiRef, CropRef, AuditEntry, PricePoint
)
from app.agents.pipeline import run_full_pipeline

router = APIRouter(tags=["Analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 2 of 2: Run the full agent pipeline for an existing farmer_crop_id.
    Returns recommendation, arbitrage table, trend data, price series, audit trail.
    """
    try:
        ctx = await run_full_pipeline(
            db,
            request.farmer_crop_id,
            transport_override=request.transport_cost_per_km_override,
            quantity_override=request.quantity_override,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")

    if not ctx.recommendation:
        raise HTTPException(500, "Pipeline completed without generating a recommendation.")

    # ── Build recommendation ───────────────────────────────────────────────
    rec = ctx.recommendation
    primary_mandi = None
    if rec.primary_mandi:
        pm = rec.primary_mandi
        primary_mandi = MandiRef(
            id=pm.id, name=pm.name, state=pm.state, district=pm.district,
            latitude=pm.latitude, longitude=pm.longitude,
        )

    recommendation_out = RecommendationResult(
        recommendation=rec.recommendation,
        headline=rec.headline,
        full_explanation=rec.full_explanation,
        primary_mandi=primary_mandi,
        projected_extra_if_hold=rec.projected_extra_if_hold,
        projected_hold_days=rec.projected_hold_days,
        perishability_warning=rec.perishability_warning,
        confidence=rec.confidence,
        disclaimer=rec.disclaimer,
    )

    # ── Build arbitrage table ─────────────────────────────────────────────
    arb_out = [
        ArbitrageResult(
            mandi_id=a.mandi_id,
            mandi_name=a.mandi_name,
            distance_km=a.distance_km,
            modal_price=a.modal_price,
            gross_revenue=a.gross_revenue,
            transport_cost=a.transport_cost,
            net_revenue=a.net_revenue,
            net_gain_over_local=a.net_gain_over_local,
            per_quintal_gain=a.per_quintal_gain,
            is_worthwhile=a.is_worthwhile,
            trend=a.trend,
            data_tier=a.data_tier,
            time_risk=a.time_risk,
        )
        for a in ctx.arbitrage_results
    ]

    # ── Build trend data ──────────────────────────────────────────────────
    trend_out = [
        TrendResult(
            mandi_id=t.mandi_id,
            mandi_name=t.mandi_name,
            trend=t.trend,
            ma7=t.ma7,
            ma30=t.ma30,
            percent_change=t.percent_change,
            is_volatile=t.is_volatile,
            volatility_ratio=t.volatility_ratio,
            confidence=t.confidence,
            days_of_data=t.days_of_data,
            gap_days=t.gap_days,
            momentum=t.momentum,
        )
        for t in ctx.trend_data.values()
    ]

    # ── Build price series ────────────────────────────────────────────────
    price_series_out: dict[int, list[PricePoint]] = {}
    for mandi_id, packet in ctx.price_data.items():
        pts = []
        for r in packet.records:
            d = r.get("arrival_date")
            if hasattr(d, "isoformat"):
                d_val = d
            else:
                from datetime import datetime as dt
                try:
                    d_val = dt.strptime(str(d), "%d/%m/%Y").date()
                except Exception:
                    continue
            pts.append(PricePoint(
                date=d_val,
                modal_price=float(r.get("modal_price", 0)),
                min_price=float(r.get("min_price")) if r.get("min_price") else None,
                max_price=float(r.get("max_price")) if r.get("max_price") else None,
                data_tier=r.get("data_tier", packet.data_tier),
            ))
        pts.sort(key=lambda x: x.date)
        price_series_out[mandi_id] = pts

    # ── Build audit trail ─────────────────────────────────────────────────
    audit_out = [
        AuditEntry(
            step_number=s.step_number,
            agent_name=s.agent_name,
            message=s.message,
            technical_detail=s.technical_detail,
            data_tier=s.data_tier,
            created_at=s.created_at,
        )
        for s in ctx.audit_trail
    ]

    # ── Build crop ref ────────────────────────────────────────────────────
    if ctx.crop:
        crop_out = CropRef(
            id=ctx.crop.id,
            canonical_name=ctx.crop.canonical_name,
            variety=ctx.crop.variety,
            is_perishable=ctx.crop.is_perishable,
            shelf_life_days=ctx.crop.shelf_life_days,
            aliases=ctx.crop.aliases,
        )
    else:
        crop_out = CropRef(
            id=1,
            canonical_name="Wheat",
            variety="Sharbati",
            is_perishable=False,
            shelf_life_days=180,
            aliases=["Wheat", "Gehun"],
        )

    # ── Local mandi ───────────────────────────────────────────────────────
    local_mandi = None
    if ctx.mandis_in_radius:
        lm = next((m for m in ctx.mandis_in_radius if m.id == ctx.home_mandi_id), ctx.mandis_in_radius[0])
        local_mandi = MandiRef(
            id=lm.id, name=lm.name, state=lm.state, district=lm.district,
            latitude=lm.latitude, longitude=lm.longitude, distance_km=lm.distance_km,
        )
    else:
        local_mandi = MandiRef(
            id=1, name="Ujjain APMC", state="Madhya Pradesh", district="Ujjain",
            latitude=23.1765, longitude=75.7885, distance_km=0.0,
        )

    # ── Compute dynamic vector trajectory forecast ───────────────────────
    from app.embeddings import find_matching_historical_trajectories
    primary_series = next(iter(price_series_out.values()), [])
    sample_prices = [p.modal_price for p in primary_series] if primary_series else [2400.0, 2420.0, 2450.0, 2480.0, 2520.0]
    traj_forecast = find_matching_historical_trajectories(sample_prices, volatility=0.02, crop_name=crop_out.canonical_name)

    response = AnalyzeResponse(
        farmer_crop_id=ctx.farmer_crop_id,
        crop=crop_out,
        quantity_quintals=ctx.quantity_quintals or 50.0,
        local_mandi=local_mandi,
        recommendation=recommendation_out,
        arbitrage_table=arb_out,
        trend_data=trend_out,
        trajectory_forecast=traj_forecast,
        price_series=price_series_out,
        overall_data_tier=ctx.overall_data_tier,
        data_tier_label=ctx.data_tier_label(),
        last_updated=datetime.utcnow(),
        audit_trail=audit_out,
        generated_at=datetime.utcnow(),
    )

    # ── Fire-and-forget: store compact snapshot for Vault analytics ───────────
    try:
        import asyncio
        rec = ctx.recommendation
        snap_payload = {
            "state": ctx.state if ctx.state else "Madhya Pradesh",
            "district": ctx.district if ctx.district else "Ujjain",
            "crop_name": crop_out.canonical_name if crop_out else "Wheat",
            "canonical_crop_id": crop_out.id if crop_out else 1,
            "recommended_action": rec.recommendation if rec else "UNKNOWN",
            "target_mandi_name": rec.primary_mandi.name if rec and rec.primary_mandi else None,
            "target_mandi_distance_km": rec.primary_mandi.distance_km if rec and rec.primary_mandi and hasattr(rec.primary_mandi, "distance_km") else None,
            "modal_price_at_run": float(arb_out[0].modal_price) if arb_out else None,
            "projected_profit_per_qtl": float(rec.projected_extra_if_hold or 0) if rec else None,
            "projected_hold_days": rec.projected_hold_days if rec else None,
            "quantity_quintals": ctx.quantity_quintals,
            "data_tier": ctx.overall_data_tier,
            "source_type": "analyze",
            "metrics": {"confidence": rec.confidence if rec else None},
        }

        async def _save_snap():
            try:
                from app.routers.vault import save_snapshot_in_background
                await save_snapshot_in_background(snap_payload)
            except Exception as snap_err:
                logger.warning(f"Vault snapshot save failed (non-fatal): {snap_err}")

        asyncio.create_task(_save_snap())
    except Exception:
        pass  # Snapshot is non-critical — never break the main response

    return response

