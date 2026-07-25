"""
app/routers/intake.py — POST /api/intake
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import IntakeRequest, IntakeResponse, NormalizationResult, CropCandidate, MandiRef
from app.agents.pipeline import run_intake_pipeline

router = APIRouter(tags=["Intake"])


@router.post("/intake", response_model=IntakeResponse)
async def intake(request: IntakeRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 1 of 2: Validate farmer input, normalize crop name, find mandis in radius.
    Returns farmer_crop_id to use in POST /api/analyze.
    """
    if request.save_profile and not request.phone_or_contact:
        raise HTTPException(422, "phone_or_contact is required when save_profile=True")

    ctx = await run_intake_pipeline(db, request)

    # Build normalization result
    norm = NormalizationResult(
        resolved=ctx.crop is not None,
        canonical_crop_id=ctx.crop.id if ctx.crop else None,
        canonical_name=ctx.crop.canonical_name if ctx.crop else None,
        variety=ctx.crop.variety if ctx.crop else None,
        similarity_score=ctx.normalization_confidence,
        top_candidates=[
            CropCandidate(
                id=c["id"],
                canonical_name=c["canonical_name"],
                variety=c.get("variety"),
                similarity_score=c.get("similarity", 0.0),
                is_perishable=c.get("is_perishable", False),
            )
            for c in ctx.normalization_candidates[:3]
        ],
        is_perishable=ctx.crop.is_perishable if ctx.crop else False,
        shelf_life_days=ctx.crop.shelf_life_days if ctx.crop else None,
        confidence=(
            "HIGH" if ctx.normalization_confidence >= 0.85
            else "MEDIUM" if ctx.normalization_confidence >= 0.75
            else "LOW"
        ),
    )

    mandi_refs = [
        MandiRef(
            id=m.id, name=m.name, state=m.state, district=m.district,
            latitude=m.latitude, longitude=m.longitude, distance_km=m.distance_km,
        )
        for m in ctx.mandis_in_radius
    ]

    audit_msg = ctx.audit_trail[-1].message if ctx.audit_trail else "Intake complete."

    return IntakeResponse(
        farmer_crop_id=ctx.farmer_crop_id,
        farmer_profile_id=ctx.farmer_profile_id,
        normalization=norm,
        mandis_in_radius=mandi_refs,
        data_tier="LIVE",
        audit_entry=audit_msg,
    )
