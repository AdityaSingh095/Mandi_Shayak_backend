"""
app/models.py
─────────────────────────────────────────────────────────
SQLAlchemy ORM models for all 7 tables.
Handles SQLite/Postgres type differences:
  - Vector(384) is only registered on Postgres; SQLite uses JSON text fallback
  - UUID is TEXT on SQLite, proper UUID on Postgres
"""

import uuid
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
    func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base
from app.config import get_settings


def _uuid_col(primary_key: bool = False, nullable: bool = True):
    """Returns a UUID column that works on both SQLite (TEXT) and Postgres (UUID)."""
    settings = get_settings()
    if settings.is_sqlite:
        return mapped_column(
            String(36),
            primary_key=primary_key,
            default=lambda: str(uuid.uuid4()),
            nullable=nullable,
        )
    return mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=primary_key,
        default=uuid.uuid4,
        nullable=nullable,
    )


def _vector_col():
    """Returns a Vector column (Postgres) or JSON text (SQLite fallback)."""
    settings = get_settings()
    if settings.is_sqlite:
        return mapped_column(Text, nullable=True)  # JSON-serialized list for SQLite
    try:
        from pgvector.sqlalchemy import Vector
        return mapped_column(Vector(384), nullable=True)
    except ImportError:
        return mapped_column(Text, nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
class Mandi(Base):
    __tablename__ = "mandis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    district: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    apmc_code: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("name", "district", name="uq_mandis_name_district"),
        Index("ix_mandis_state_district", "state", "district"),
    )

    price_records: Mapped[List["PriceRecord"]] = relationship("PriceRecord", back_populates="mandi")


class CropCanon(Base):
    __tablename__ = "crop_canon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    variety: Mapped[Optional[str]] = mapped_column(Text)
    is_perishable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shelf_life_days: Mapped[Optional[int]] = mapped_column(Integer)
    aliases_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of strings
    embedding_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of floats (SQLite)
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("canonical_name", "variety", name="uq_crop_variety"),
    )

    price_records: Mapped[List["PriceRecord"]] = relationship("PriceRecord", back_populates="canonical_crop")
    farmer_crops: Mapped[List["FarmerCrop"]] = relationship("FarmerCrop", back_populates="canonical_crop")

    def get_aliases(self) -> list[str]:
        import json
        if self.aliases_json:
            try:
                return json.loads(self.aliases_json)
            except Exception:
                return []
        return []

    def set_aliases(self, aliases: list[str]):
        import json
        self.aliases_json = json.dumps(aliases)

    def get_embedding(self) -> list[float] | None:
        import json
        if self.embedding_json:
            try:
                return json.loads(self.embedding_json)
            except Exception:
                return None
        return None

    def set_embedding(self, vector: list[float]):
        import json
        self.embedding_json = json.dumps(vector)


class PriceRecord(Base):
    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    raw_commodity_name: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_crop_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("crop_canon.id", ondelete="SET NULL"))
    mandi_id: Mapped[int] = mapped_column(Integer, ForeignKey("mandis.id", ondelete="RESTRICT"), nullable=False, index=True)
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    min_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    max_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    modal_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    data_tier: Mapped[str] = mapped_column(Text, nullable=False, default="LIVE")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="data.gov.in")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("raw_commodity_name", "mandi_id", "arrival_date", name="uq_price_record"),
        Index("ix_price_crop_mandi_date", "canonical_crop_id", "mandi_id", "arrival_date"),
        Index("ix_price_mandi_date", "mandi_id", "arrival_date"),
    )

    mandi: Mapped["Mandi"] = relationship("Mandi", back_populates="price_records")
    canonical_crop: Mapped[Optional["CropCanon"]] = relationship("CropCanon", back_populates="price_records")


class FarmerProfile(Base):
    __tablename__ = "farmer_profiles"

    id: Mapped[str] = _uuid_col(primary_key=True, nullable=False)
    phone_or_contact: Mapped[Optional[str]] = mapped_column(Text)
    village: Mapped[Optional[str]] = mapped_column(Text)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    travel_radius_km: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    transport_cost_per_km: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=18.0)
    notification_channel: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pending_notification: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crops: Mapped[List["FarmerCrop"]] = relationship("FarmerCrop", back_populates="farmer", cascade="all, delete-orphan")


class FarmerCrop(Base):
    __tablename__ = "farmer_crops"

    id: Mapped[str] = _uuid_col(primary_key=True, nullable=False)
    farmer_id: Mapped[Optional[str]] = mapped_column(
        String(36) if get_settings().is_sqlite else PG_UUID(as_uuid=True),
        ForeignKey("farmer_profiles.id", ondelete="CASCADE"),
    )
    canonical_crop_id: Mapped[int] = mapped_column(Integer, ForeignKey("crop_canon.id", ondelete="RESTRICT"), nullable=False)
    home_mandi_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("mandis.id", ondelete="SET NULL"))
    quantity_quintals: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    readiness_date: Mapped[Optional[date]] = mapped_column(Date)
    last_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    last_recommendation_detail: Mapped[Optional[str]] = mapped_column(Text)
    last_recommendation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    farmer: Mapped[Optional["FarmerProfile"]] = relationship("FarmerProfile", back_populates="crops")
    canonical_crop: Mapped["CropCanon"] = relationship("CropCanon", back_populates="farmer_crops")
    audit_entries: Mapped[List["AuditTrail"]] = relationship("AuditTrail", back_populates="farmer_crop", cascade="all, delete-orphan")


class AuditTrail(Base):
    __tablename__ = "audit_trail"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    farmer_crop_id: Mapped[str] = mapped_column(
        String(36) if get_settings().is_sqlite else PG_UUID(as_uuid=True),
        ForeignKey("farmer_crops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(36))
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    technical_detail: Mapped[Optional[str]] = mapped_column(Text)
    data_tier: Mapped[str] = mapped_column(Text, nullable=False, default="LIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_audit_session", "session_id", "step_number"),
    )

    farmer_crop: Mapped["FarmerCrop"] = relationship("FarmerCrop", back_populates="audit_entries")


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(Text)
