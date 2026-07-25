"""
app/routers/profiles.py — POST /api/profile/save, DELETE /api/profile/{id}
"""

import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import FarmerProfile, FarmerCrop
from app.schemas import SaveProfileRequest, ProfileResponse, DeleteProfileResponse

router = APIRouter(tags=["Profiles"])


@router.post("/profile/save", response_model=ProfileResponse)
async def save_profile(request: SaveProfileRequest, db: AsyncSession = Depends(get_db)):
    """
    Save a farmer profile with explicit monitoring consent.
    Requires consent_given=True — this is an intentional UX gate.
    """
    if not request.consent_given:
        raise HTTPException(400, "Explicit consent (consent_given=True) is required to save a profile.")

    # Find the farmer_crop
    fc = await db.get(FarmerCrop, request.farmer_crop_id)
    if not fc:
        raise HTTPException(404, "farmer_crop_id not found. Complete /api/intake first.")

    # Check if profile exists for this farmer_crop
    if fc.farmer_id:
        profile = await db.get(FarmerProfile, fc.farmer_id)
        if profile:
            profile.phone_or_contact = request.phone_or_contact
            profile.notification_channel = request.notification_channel
            profile.consent_given = True
            profile.consent_given_at = datetime.utcnow()
            profile.updated_at = datetime.utcnow()
            await db.commit()
            return ProfileResponse(
                farmer_profile_id=str(profile.id),
                farmer_crop_id=request.farmer_crop_id,
                message="Profile updated. Monitoring active.",
            )

    # Create new profile
    profile = FarmerProfile(
        phone_or_contact=request.phone_or_contact,
        district="",
        state="",
        notification_channel=request.notification_channel,
        consent_given=True,
        consent_given_at=datetime.utcnow(),
    )
    db.add(profile)
    await db.flush()  # Get the generated ID

    fc.farmer_id = profile.id
    await db.commit()

    return ProfileResponse(
        farmer_profile_id=str(profile.id),
        farmer_crop_id=request.farmer_crop_id,
        message="Profile saved. You will be notified when your recommendation changes.",
    )


@router.delete("/profile/{farmer_profile_id}", response_model=DeleteProfileResponse)
async def delete_profile(farmer_profile_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete a farmer profile. Hard-deleted by cron after 30 days."""
    profile = await db.get(FarmerProfile, farmer_profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found.")

    profile.deleted_at = datetime.utcnow()
    profile.consent_given = False
    await db.commit()

    return DeleteProfileResponse(
        message="Profile deleted. Monitoring stopped. Data will be permanently removed within 30 days.",
        deleted_at=profile.deleted_at,
    )


@router.get("/profile/{farmer_profile_id}/notification")
async def get_notification(farmer_profile_id: str, db: AsyncSession = Depends(get_db)):
    """Read and clear pending in-app notification for a farmer profile."""
    profile = await db.get(FarmerProfile, farmer_profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found.")

    notification = None
    if profile.pending_notification:
        try:
            notification = json.loads(profile.pending_notification)
        except Exception:
            notification = None

    # Clear the notification
    profile.pending_notification = None
    await db.commit()

    return {"notification": notification}
