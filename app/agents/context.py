"""
app/agents/context.py
─────────────────────────────────────────────────────────
PipelineContext — shared state object passed between all agents.
No agent reads from another agent's internals; they only write to
and read from this shared context object.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Any


@dataclass
class AuditStep:
    step_number: int
    agent_name: str
    message: str
    technical_detail: Optional[str] = None
    data_tier: str = "LIVE"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MandiInfo:
    id: int
    name: str
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None


@dataclass
class CropInfo:
    id: int
    canonical_name: str
    variety: Optional[str] = None
    is_perishable: bool = False
    shelf_life_days: Optional[int] = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class PriceDataPacket:
    mandi_id: int
    mandi_name: str
    records: list[dict]  # [{date, modal_price, min_price, max_price}]
    data_tier: str  # LIVE | CACHE | CACHE_STALE | DEMO
    data_gap: bool = False
    last_updated: Optional[datetime] = None


@dataclass
class TrendData:
    mandi_id: int
    mandi_name: str
    trend: str  # RISING | FALLING | STABLE | INSUFFICIENT_DATA
    ma7: Optional[float] = None
    ma30: Optional[float] = None
    percent_change: Optional[float] = None
    is_volatile: bool = False
    volatility_ratio: Optional[float] = None
    confidence: str = "LOW"  # HIGH | MEDIUM | LOW
    days_of_data: int = 0
    gap_days: int = 0
    momentum: Optional[str] = None


@dataclass
class ArbitrageData:
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


@dataclass
class RecommendationData:
    recommendation: str  # SELL_NOW | SELL_LOCAL | HOLD | TRAVEL | CONSIDER_TRAVEL | MONITOR | INSUFFICIENT_DATA
    headline: str
    full_explanation: str
    primary_mandi: Optional[MandiInfo] = None
    projected_extra_if_hold: Optional[float] = None
    projected_hold_days: Optional[int] = None
    perishability_warning: bool = False
    confidence: str = "LOW"
    disclaimer: str = (
        "This recommendation is advisory only. Based on reported Agmarknet data. "
        "Does not guarantee future price movement."
    )


@dataclass
class PipelineContext:
    """Shared state passed through the agent pipeline. Agents append to audit_trail."""

    # ── Set by Agent 1 (Intake) ───────────────────────────────────────────────
    farmer_crop_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    farmer_profile_id: Optional[str] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    district: str = ""
    state: str = ""
    farmer_lat: Optional[float] = None
    farmer_lon: Optional[float] = None
    travel_radius_km: int = 50
    quantity_quintals: float = 0.0
    transport_cost_per_km: float = 18.0
    readiness_date: Optional[date] = None
    mandis_in_radius: list[MandiInfo] = field(default_factory=list)
    home_mandi_id: Optional[int] = None

    # ── Set by Agent 3 (Normalization) ────────────────────────────────────────
    crop: Optional[CropInfo] = None
    normalization_confidence: float = 0.0
    normalization_candidates: list[dict] = field(default_factory=list)

    # ── Set by Agent 2 (Price Fetch) ──────────────────────────────────────────
    price_data: dict[int, PriceDataPacket] = field(default_factory=dict)  # mandi_id → packet
    overall_data_tier: str = "LIVE"

    # ── Set by Agent 4 (Trend) ────────────────────────────────────────────────
    trend_data: dict[int, TrendData] = field(default_factory=dict)  # mandi_id → trend

    # ── Set by Agent 5 (Arbitrage) ────────────────────────────────────────────
    arbitrage_results: list[ArbitrageData] = field(default_factory=list)

    # ── Set by Agent 6 (Recommendation) ──────────────────────────────────────
    recommendation: Optional[RecommendationData] = None

    # ── Accumulated by all agents ─────────────────────────────────────────────
    audit_trail: list[AuditStep] = field(default_factory=list)
    _step_counter: int = field(default=0, repr=False)

    def append_audit(
        self,
        agent_name: str,
        message: str,
        technical_detail: Optional[str] = None,
        data_tier: Optional[str] = None,
    ):
        self._step_counter += 1
        tier = data_tier or self.overall_data_tier or "LIVE"
        self.audit_trail.append(AuditStep(
            step_number=self._step_counter,
            agent_name=agent_name,
            message=message,
            technical_detail=technical_detail,
            data_tier=tier,
        ))

    def worst_data_tier(self) -> str:
        """Returns the 'worst' (least fresh) tier seen across all price packets."""
        tier_priority = {"LIVE": 0, "CACHE": 1, "CACHE_STALE": 2, "DEMO": 3}
        worst = "LIVE"
        for packet in self.price_data.values():
            if tier_priority.get(packet.data_tier, 0) > tier_priority.get(worst, 0):
                worst = packet.data_tier
        return worst

    def data_tier_label(self) -> str:
        labels = {
            "LIVE": "Live Agmarknet Data",
            "CACHE": "Cached Data",
            "CACHE_STALE": "Stale Cached Data (Live fetch failed)",
            "DEMO": "⚠️ DEMO DATA — Not real-time",
        }
        return labels.get(self.overall_data_tier, self.overall_data_tier)
