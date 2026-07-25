"""
app/schemas.py
─────────────────────────────────────────────────────────
All Pydantic v2 request/response models.
"""

from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, Literal, Any
from uuid import UUID


# ── Shared references ─────────────────────────────────────────────────────────

class MandiRef(BaseModel):
    id: int
    name: str
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None


class CropRef(BaseModel):
    id: int
    canonical_name: str
    variety: Optional[str] = None
    is_perishable: bool
    shelf_life_days: Optional[int] = None
    aliases: list[str] = []


class AuditEntry(BaseModel):
    step_number: int
    agent_name: str
    message: str
    technical_detail: Optional[str] = None
    data_tier: str
    created_at: Optional[datetime] = None


class PricePoint(BaseModel):
    date: date
    modal_price: float
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    data_tier: str = "LIVE"


# ── Intake ────────────────────────────────────────────────────────────────────

class IntakeRequest(BaseModel):
    crop_raw_name: str = Field(..., min_length=2, max_length=100)
    variety_hint: Optional[str] = Field(None, max_length=50)
    district: str = Field(..., min_length=2)
    state: str = Field(..., min_length=2)
    travel_radius_km: int = Field(50, ge=5, le=150)
    quantity_quintals: Optional[float] = Field(None, gt=0, le=10000)
    readiness_date: Optional[date] = None
    transport_cost_per_km: float = Field(18.0, ge=1.0, le=200.0)
    save_profile: bool = False
    phone_or_contact: Optional[str] = None
    notification_channel: Literal["sms", "email", "in_app", "none"] = "none"


class CropCandidate(BaseModel):
    id: int
    canonical_name: str
    variety: Optional[str] = None
    similarity_score: float
    is_perishable: bool


class NormalizationResult(BaseModel):
    resolved: bool
    canonical_crop_id: Optional[int] = None
    canonical_name: Optional[str] = None
    variety: Optional[str] = None
    similarity_score: float = 0.0
    top_candidates: list[CropCandidate] = []
    is_perishable: bool = False
    shelf_life_days: Optional[int] = None
    confidence: Optional[str] = None


class IntakeResponse(BaseModel):
    farmer_crop_id: str
    farmer_profile_id: Optional[str] = None
    normalization: NormalizationResult
    mandis_in_radius: list[MandiRef]
    data_tier: str
    audit_entry: str


# ── Analysis ──────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    farmer_crop_id: str
    transport_cost_per_km_override: Optional[float] = None
    quantity_override: Optional[float] = None


class TrendResult(BaseModel):
    mandi_id: int
    mandi_name: str
    trend: Literal["RISING", "FALLING", "STABLE", "INSUFFICIENT_DATA"]
    ma7: Optional[float] = None
    ma30: Optional[float] = None
    percent_change: Optional[float] = None
    is_volatile: bool = False
    volatility_ratio: Optional[float] = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    days_of_data: int = 0
    gap_days: int = 0
    momentum: Optional[str] = None


class ArbitrageResult(BaseModel):
    mandi_id: int
    mandi_name: str
    distance_km: float
    modal_price: float
    gross_revenue: float
    transport_cost: float
    net_revenue: float
    net_gain_over_local: float
    per_quintal_gain: float
    is_worthwhile: bool
    trend: str
    data_tier: str
    time_risk: bool = False


class RecommendationResult(BaseModel):
    recommendation: Literal[
        "SELL_NOW", "SELL_LOCAL", "HOLD", "TRAVEL",
        "CONSIDER_TRAVEL", "MONITOR", "INSUFFICIENT_DATA"
    ]
    headline: str
    full_explanation: str
    primary_mandi: Optional[MandiRef] = None
    projected_extra_if_hold: Optional[float] = None
    projected_hold_days: Optional[int] = None
    perishability_warning: bool = False
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    disclaimer: str = (
        "This recommendation is advisory only. Based on reported Agmarknet data. "
        "Does not guarantee future price movement."
    )


class AnalyzeResponse(BaseModel):
    farmer_crop_id: str
    crop: CropRef
    quantity_quintals: float = 50.0
    local_mandi: Optional[MandiRef] = None
    recommendation: RecommendationResult
    arbitrage_table: list[ArbitrageResult]
    trend_data: list[TrendResult]
    trajectory_forecast: Optional[dict] = None
    price_series: dict[int, list[PricePoint]]
    overall_data_tier: str
    data_tier_label: str
    last_updated: Optional[datetime] = None
    audit_trail: list[AuditEntry]
    generated_at: datetime


# ── History ───────────────────────────────────────────────────────────────────

class MAPoint(BaseModel):
    date: date
    value: float


class MandiPriceSeries(BaseModel):
    mandi_id: int
    mandi_name: str
    data: list[PricePoint]
    data_completeness_pct: float


class HistoryResponse(BaseModel):
    crop: CropRef
    series: list[MandiPriceSeries]
    ma7_series: dict[int, list[MAPoint]]
    ma30_series: dict[int, list[MAPoint]]
    overall_data_tier: str


# ── Profile ───────────────────────────────────────────────────────────────────

class SaveProfileRequest(BaseModel):
    farmer_crop_id: str
    phone_or_contact: str = Field(..., min_length=5)
    notification_channel: Literal["sms", "email", "in_app"]
    consent_given: bool


class ProfileResponse(BaseModel):
    farmer_profile_id: str
    farmer_crop_id: str
    message: str


class DeleteProfileResponse(BaseModel):
    message: str
    deleted_at: datetime


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    data_gov_api: str
    database: str
    environment: str
    timestamp: datetime
