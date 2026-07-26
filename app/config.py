"""
app/config.py
─────────────────────────────────────────────────────────
Settings loaded from .env / environment variables.
Supports explicit USE_LOCAL_DB toggle:
  - USE_LOCAL_DB=true  → SQLite database + local JSON embedding storage
  - USE_LOCAL_DB=false → PostgreSQL (Supabase) + pgvector embedding storage
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database Toggle & Connection URLs ─────────────────────────────────────
    use_local_db: bool = True  # If True: local SQLite + JSON vectors. If False: Postgres + pgvector
    database_url: str = "sqlite+aiosqlite:///./mandi_sahayak.db"
    database_url_direct: str = ""  # Direct connection for Alembic migrations (Postgres)

    # ── External APIs ─────────────────────────────────────────────────────────
    data_gov_in_api_key: str = "579b464db66ec23bdd000001fa94444d6da043e46831fa166ead8453"

    # ── App Settings ──────────────────────────────────────────────────────────
    environment: str = "local"
    cron_secret: str = "changeme"
    force_demo_data: bool = False  # Override: always use demo data

    @property
    def is_sqlite(self) -> bool:
        # Enforce PostgreSQL exclusively
        return False

    @property
    def effective_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# ─── Runtime config (agent thresholds loaded from system_config table) ──────
_runtime_config: dict[str, str] = {
    "trend.rising_threshold_pct": "2.5",
    "trend.falling_threshold_pct": "-2.5",
    "trend.volatility_threshold_ratio": "0.05",
    "trend.min_days_for_analysis": "7",
    "trend.gap_interpolation_max_days": "2",
    "arbitrage.min_worthwhile_gain_inr": "500",
    "arbitrage.strong_travel_gain_inr": "1000",
    "transport.default_own_vehicle_per_km": "12",
    "transport.default_hired_per_km": "20",
    "cache.price_freshness_hours": "6",
    "cache.stale_threshold_hours": "48",
    "normalization.auto_resolve_threshold": "0.85",
    "normalization.confirm_threshold": "0.75",
    "normalization.reject_threshold": "0.60",
    "retention.price_records_days": "180",
    "retention.audit_trail_days": "90",
}


async def load_runtime_config(db) -> dict[str, str]:
    """Load all system_config rows into the in-memory cache. Call once per request."""
    global _runtime_config
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT key, value FROM system_config"))
        rows = result.mappings().all()
        if rows:
            _runtime_config.update({row["key"]: row["value"] for row in rows})
    except Exception:
        pass  # Silently keep defaults during initial setup
    return _runtime_config


def cfg(key: str, default: str = "") -> str:
    return _runtime_config.get(key, default)


def cfg_float(key: str, default: float = 0.0) -> float:
    try:
        return float(_runtime_config.get(key, str(default)))
    except ValueError:
        return default


def cfg_int(key: str, default: int = 0) -> int:
    try:
        return int(_runtime_config.get(key, str(default)))
    except ValueError:
        return default
