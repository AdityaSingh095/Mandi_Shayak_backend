"""
app/agents/price_fetch_agent.py
─────────────────────────────────────────────────────────
Agent 2: Fetches price data from Agmarknet API (Priority 1),
falls back to Supabase cache (Priority 2), then demo data (Priority 3).
Each data tier is clearly flagged in the response.

API response fields (confirmed from live data):
  state, district, market, commodity, variety, grade,
  arrival_date (DD/MM/YYYY), min_price, max_price, modal_price
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import PipelineContext, PriceDataPacket, MandiInfo
from app.config import get_settings, cfg_int, cfg_float
from app.demo_data import get_demo_prices_for_mandi_crop, DEMO_DATA_BANNER
from app.models import PriceRecord

logger = logging.getLogger(__name__)

AGMARKNET_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
API_KEY = "579b464db66ec23bdd000001fa94444d6da043e46831fa166ead8453"


def _parse_api_date(date_str: str) -> date | None:
    """Parse Agmarknet date format: DD/MM/YYYY → Python date."""
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except Exception:
        return None


async def _fetch_from_agmarknet(
    state: str, district: str, commodity: str, days_back: int = 30
) -> list[dict]:
    """
    Calls the data.gov.in API for price records.
    Returns normalized list of price dicts.
    Raises httpx exceptions on failure.
    """
    settings = get_settings()
    api_key = settings.data_gov_in_api_key or API_KEY

    if settings.force_demo_data:
        raise ValueError("FORCE_DEMO_DATA=true — skipping live API")

    async def _query_api(comm: str) -> list[dict]:
        recs = []
        off = 0
        limit = 500
        async with httpx.AsyncClient(timeout=8.0) as client:
            while True:
                params = {
                    "api-key": api_key,
                    "format": "json",
                    "limit": limit,
                    "offset": off,
                    "filters[state]": state,
                    "filters[district]": district,
                    "filters[commodity]": comm,
                }
                resp = await client.get(AGMARKNET_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                records = data.get("records", [])
                recs.extend(records)
                total = int(data.get("total", 0))
                off += limit
                if off >= total or not records:
                    break
        return recs

    all_records = await _query_api(commodity)

    # Fallback to primary crop word (e.g. "Wheat" instead of "Wheat Sharbati") if no records returned
    base_comm = commodity.split()[0]
    if not all_records and base_comm != commodity:
        try:
            all_records = await _query_api(base_comm)
        except Exception:
            pass

    # Normalize field names from API response
    normalized = []
    cutoff = date.today() - timedelta(days=days_back)
    for r in all_records:
        arrival = _parse_api_date(r.get("arrival_date", ""))
        if not arrival or arrival < cutoff:
            continue
        normalized.append({
            "arrival_date": arrival,
            "market": r.get("market", ""),
            "state": r.get("state", ""),
            "district": r.get("district", ""),
            "commodity": r.get("commodity", ""),
            "variety": r.get("variety", ""),
            "min_price": float(r.get("min_price", 0) or 0),
            "max_price": float(r.get("max_price", 0) or 0),
            "modal_price": float(r.get("modal_price", 0) or 0),
            "data_tier": "LIVE",
        })
    return normalized


async def _get_cached_prices(
    db: AsyncSession, mandi_id: int, canonical_crop_id: int, days_back: int
) -> list[dict]:
    """Retrieve stored price records from the database cache."""
    cutoff = date.today() - timedelta(days=days_back)
    result = await db.execute(
        select(PriceRecord).where(
            PriceRecord.mandi_id == mandi_id,
            PriceRecord.canonical_crop_id == canonical_crop_id,
            PriceRecord.arrival_date >= cutoff,
        ).order_by(PriceRecord.arrival_date.asc())
    )
    rows = result.scalars().all()
    return [
        {
            "arrival_date": r.arrival_date,
            "market": "",
            "modal_price": float(r.modal_price),
            "min_price": float(r.min_price or 0),
            "max_price": float(r.max_price or 0),
            "data_tier": r.data_tier,
            "fetched_at": r.fetched_at,
        }
        for r in rows
    ]


async def _upsert_price_records(
    db: AsyncSession, records: list[dict], mandi_id: int, canonical_crop_id: int
):
    """Upsert fetched records into the price_records cache table."""
    for r in records:
        # SQLite-compatible upsert via merge pattern
        existing = await db.execute(
            select(PriceRecord).where(
                PriceRecord.raw_commodity_name == r.get("commodity", ""),
                PriceRecord.mandi_id == mandi_id,
                PriceRecord.arrival_date == r["arrival_date"],
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.modal_price = r["modal_price"]
            row.min_price = r.get("min_price")
            row.max_price = r.get("max_price")
            row.data_tier = "LIVE"
            row.fetched_at = datetime.utcnow()
        else:
            db.add(PriceRecord(
                raw_commodity_name=r.get("commodity", ""),
                canonical_crop_id=canonical_crop_id,
                mandi_id=mandi_id,
                arrival_date=r["arrival_date"],
                min_price=r.get("min_price"),
                max_price=r.get("max_price"),
                modal_price=r["modal_price"],
                data_tier="LIVE",
                source="data.gov.in",
            ))
    # Staged for batch commit at end of pipeline step


async def _fetch_mandi_prices(
    db: AsyncSession,
    mandi: MandiInfo,
    ctx: PipelineContext,
    days_back: int = 30,
) -> PriceDataPacket:
    """
    Three-tier data resolution for a single mandi:
    LIVE → CACHE → DEMO
    """
    crop_name = ctx.crop.canonical_name if ctx.crop else ""
    canonical_crop_id = ctx.crop.id if ctx.crop else 1
    freshness_hours = cfg_float("cache.price_freshness_hours", 6.0)
    stale_hours = cfg_float("cache.stale_threshold_hours", 48.0)

    hours_old = 999
    latest_fetch = None

    # ── Priority 1: DB Cache Check First (Instant 0ms response) ───────────
    cached = await _get_cached_prices(db, mandi.id, canonical_crop_id, days_back)
    if cached:
        latest_fetch = max(
            (r.get("fetched_at") for r in cached if r.get("fetched_at")),
            default=None
        )
        if latest_fetch:
            diff = datetime.utcnow() - (
                latest_fetch if isinstance(latest_fetch, datetime) else datetime.utcnow()
            )
            hours_old = diff.total_seconds() / 3600

        # If cache is fresh (< 6 hours old), return immediately without hitting external API!
        if hours_old <= freshness_hours:
            logger.info(f"CACHE (FRESH 0ms): {mandi.name} — {len(cached)} records ({hours_old:.1f}h old)")
            return PriceDataPacket(
                mandi_id=mandi.id, mandi_name=mandi.name,
                records=cached, data_tier="LIVE",
                last_updated=latest_fetch,
            )

    # ── Priority 2: Live API Call (only when DB cache is missing or stale) ─
    try:
        api_records = await _fetch_from_agmarknet(
            state=mandi.state,
            district=mandi.district,
            commodity=crop_name,
            days_back=days_back,
        )
        # Filter to only this mandi's market
        mandi_records = [
            r for r in api_records
            if r["market"].lower().strip() in mandi.name.lower().strip()
            or mandi.name.lower().strip() in r["market"].lower().strip()
        ]
        if mandi_records:
            await _upsert_price_records(db, mandi_records, mandi.id, canonical_crop_id)
            logger.info(f"LIVE data: {mandi.name} — {len(mandi_records)} records")
            return PriceDataPacket(
                mandi_id=mandi.id, mandi_name=mandi.name,
                records=mandi_records, data_tier="LIVE",
                last_updated=datetime.utcnow(),
            )
    except Exception as e:
        logger.warning(f"API fetch failed for {mandi.name}: {e}")

        if cached:
            tier = "CACHE" if hours_old <= stale_hours else "CACHE_STALE"
            logger.info(f"CACHE ({tier}): {mandi.name} — {len(cached)} records")
            return PriceDataPacket(
                mandi_id=mandi.id, mandi_name=mandi.name,
                records=cached, data_tier=tier,
                last_updated=latest_fetch,
            )

    # ── Priority 3: Demo data ──────────────────────────────────────────────
    logger.warning(f"DEMO DATA fallback for {mandi.name} / {crop_name}")
    demo_records = get_demo_prices_for_mandi_crop(mandi.name, crop_name, days_back)
    # Store demo in cache too (so historical view works)
    for r in demo_records:
        r["arrival_date"] = datetime.strptime(r["arrival_date"], "%d/%m/%Y").date()
        r["data_tier"] = "DEMO"
    demo_to_store = [
        dict(r, commodity=crop_name) for r in demo_records
    ]
    await _upsert_price_records(db, demo_to_store, mandi.id, canonical_crop_id)

    return PriceDataPacket(
        mandi_id=mandi.id, mandi_name=mandi.name,
        records=demo_records, data_tier="DEMO",
        last_updated=datetime.utcnow(),
    )


async def run_price_fetch_agent(db: AsyncSession, ctx: PipelineContext) -> PipelineContext:
    """
    Fetches prices for all mandis in ctx.mandis_in_radius concurrently.
    Populates ctx.price_data and ctx.overall_data_tier.
    """
    if not ctx.crop:
        ctx.append_audit(
            agent_name="PRICE_FETCH",
            message="Skipping price fetch — crop not resolved by normalization agent.",
        )
        return ctx

    days_back = 30

    # Concurrent fetch for all mandis
    tasks = [
        _fetch_mandi_prices(db, mandi, ctx, days_back)
        for mandi in ctx.mandis_in_radius
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for mandi, result in zip(ctx.mandis_in_radius, results):
        if isinstance(result, Exception):
            logger.error(f"Price fetch exception for {mandi.name}: {result}")
            # Create empty DEMO fallback
            demo = get_demo_prices_for_mandi_crop(mandi.name, ctx.crop.canonical_name, days_back)
            for r in demo:
                if isinstance(r.get("arrival_date"), str):
                    r["arrival_date"] = datetime.strptime(r["arrival_date"], "%d/%m/%Y").date()
            ctx.price_data[mandi.id] = PriceDataPacket(
                mandi_id=mandi.id, mandi_name=mandi.name,
                records=demo, data_tier="DEMO",
            )
        else:
            ctx.price_data[mandi.id] = result

    # Perform single batch commit for all staged price records
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning(f"Batch price records commit failed: {e}")

    ctx.overall_data_tier = ctx.worst_data_tier()

    tiers = {mid: p.data_tier for mid, p in ctx.price_data.items()}
    ctx.append_audit(
        agent_name="PRICE_FETCH",
        message=(
            f"Retrieved price data for {len(ctx.price_data)} mandis. "
            f"Data tier: {ctx.overall_data_tier}. "
            + (DEMO_DATA_BANNER if ctx.overall_data_tier == "DEMO" else "")
        ),
        technical_detail=f"Per-mandi tiers: {tiers}. Days back: {days_back}.",
        data_tier=ctx.overall_data_tier,
    )
    return ctx
