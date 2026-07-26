"""
app/agents/history_agent.py — Bug-fixed 3-tier data resolution
───────────────────────────────────────────────────────────────
Per mandi:
  Tier 1 — DB cache hit (fetched_at within CACHE_TTL_HOURS) → return instantly, skip API
  Tier 2 — Live Agmarknet HTTP API → upsert into DB → return LIVE
  Tier 3 — Demo fallback ONLY if API fails and no stale cache exists

Bugs fixed vs. previous version:
  1. datetime timezone-awareness mismatch: fetched_at is timezone-aware (Supabase UTC),
     datetime.utcnow() is naive — replaced with datetime.now(UTC) consistently.
  2. _is_cache_fresh used r.fetched_at.replace(tzinfo=None) but rows are ORM objects —
     now handles both naive and aware datetimes safely.
  3. _upsert_price_records not committed in history path — now commits after each mandi.
  4. CACHE_TTL_HOURS was defined twice (inside planner loop) — centralised here.
  5. Empty data list causes ZeroDivisionError in completeness calc — guarded.
  6. Vercel 10s execution limit: serial per-mandi API calls could exceed limit for 8 mandis
     — replaced inner loop with asyncio.gather for concurrent API calls.
"""

import asyncio
import logging
from datetime import date, timedelta, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceRecord, CropCanon, Mandi

logger = logging.getLogger(__name__)

# Single source of truth for cache TTL
CACHE_TTL_HOURS = 6.0


# ─── State → Mandi lookup table (moved to module level — computed once) ───────
STATE_ALL_MANDIS: dict[str, list[dict]] = {
    'Madhya Pradesh': [
        {'id': 1,  'name': 'Ujjain APMC',    'district': 'Ujjain'},
        {'id': 2,  'name': 'Dewas Mandi',     'district': 'Dewas'},
        {'id': 3,  'name': 'Indore Mandi',    'district': 'Indore'},
        {'id': 4,  'name': 'Bhopal APMC',     'district': 'Bhopal'},
        {'id': 21, 'name': 'Gwalior Mandi',   'district': 'Gwalior'},
        {'id': 22, 'name': 'Jabalpur APMC',   'district': 'Jabalpur'},
        {'id': 23, 'name': 'Mandsaur Mandi',  'district': 'Mandsaur'},
        {'id': 24, 'name': 'Ratlam APMC',     'district': 'Ratlam'},
    ],
    'Maharashtra': [
        {'id': 5,  'name': 'Nashik APMC',     'district': 'Nashik'},
        {'id': 6,  'name': 'Pune Mandi',      'district': 'Pune'},
        {'id': 7,  'name': 'Nagpur APMC',     'district': 'Nagpur'},
        {'id': 8,  'name': 'Aurangabad Mandi','district': 'Aurangabad'},
        {'id': 25, 'name': 'Amravati APMC',   'district': 'Amravati'},
        {'id': 26, 'name': 'Solapur Mandi',   'district': 'Solapur'},
        {'id': 27, 'name': 'Kolhapur APMC',   'district': 'Kolhapur'},
        {'id': 28, 'name': 'Latur Mandi',     'district': 'Latur'},
    ],
    'Punjab': [
        {'id': 9,  'name': 'Ludhiana APMC',   'district': 'Ludhiana'},
        {'id': 10, 'name': 'Amritsar Mandi',  'district': 'Amritsar'},
        {'id': 11, 'name': 'Jalandhar APMC',  'district': 'Jalandhar'},
        {'id': 12, 'name': 'Patiala Mandi',   'district': 'Patiala'},
        {'id': 29, 'name': 'Bathinda APMC',   'district': 'Bathinda'},
        {'id': 30, 'name': 'Sangrur Mandi',   'district': 'Sangrur'},
    ],
    'Haryana': [
        {'id': 13, 'name': 'Karnal APMC',     'district': 'Karnal'},
        {'id': 14, 'name': 'Ambala Mandi',    'district': 'Ambala'},
        {'id': 15, 'name': 'Hisar APMC',      'district': 'Hisar'},
        {'id': 16, 'name': 'Rohtak Mandi',    'district': 'Rohtak'},
        {'id': 31, 'name': 'Sirsa APMC',      'district': 'Sirsa'},
        {'id': 32, 'name': 'Panipat Mandi',   'district': 'Panipat'},
    ],
    'Uttar Pradesh': [
        {'id': 17, 'name': 'Agra APMC',       'district': 'Agra'},
        {'id': 18, 'name': 'Kanpur Mandi',    'district': 'Kanpur'},
        {'id': 19, 'name': 'Varanasi APMC',   'district': 'Varanasi'},
        {'id': 20, 'name': 'Lucknow Mandi',   'district': 'Lucknow'},
        {'id': 33, 'name': 'Aligarh APMC',    'district': 'Aligarh'},
        {'id': 34, 'name': 'Bareilly Mandi',  'district': 'Bareilly'},
    ],
}

# Flat id→info lookup built once at import time
FLAT_MANDI_LOOKUP: dict[int, dict] = {
    m['id']: {**m, 'state': st}
    for st, mandis in STATE_ALL_MANDIS.items()
    for m in mandis
}


def _compute_moving_average(prices: list[tuple[date, float]], window: int) -> list[dict]:
    result = []
    values = []
    for d, price in prices:
        values.append(price)
        window_vals = values[-window:] if len(values) >= window else values
        result.append({"date": d.isoformat(), "value": round(sum(window_vals) / len(window_vals), 2)})
    return result


async def _get_cached_records(
    db: AsyncSession, mandi_id: int, canonical_crop_id: int, cutoff: date
) -> list:
    """Return ORM PriceRecord rows from DB for this mandi/crop since cutoff."""
    result = await db.execute(
        select(PriceRecord).where(
            PriceRecord.mandi_id == mandi_id,
            PriceRecord.canonical_crop_id == canonical_crop_id,
            PriceRecord.arrival_date >= cutoff,
        ).order_by(PriceRecord.arrival_date.asc())
    )
    return result.scalars().all()


def _is_cache_fresh(rows: list) -> bool:
    """True if the most recently fetched LIVE/CACHE row is < CACHE_TTL_HOURS old.
    BUG FIX: handles both timezone-aware (Supabase Postgres) and naive (SQLite) datetimes.
    """
    now_utc = datetime.now(timezone.utc)
    live_rows = [r for r in rows if getattr(r, 'data_tier', 'LIVE') != 'DEMO']
    if not live_rows:
        return False

    fetched_ats = []
    for r in live_rows:
        fa = getattr(r, 'fetched_at', None)
        if fa is None:
            continue
        # Make timezone-aware if naive
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        fetched_ats.append(fa)

    if not fetched_ats:
        return False

    latest = max(fetched_ats)
    age_hours = (now_utc - latest).total_seconds() / 3600
    return age_hours < CACHE_TTL_HOURS


def _rows_to_data(rows: list) -> list[dict]:
    return [
        {
            "date": r.arrival_date.isoformat(),
            "modal_price": float(r.modal_price),
            "min_price": float(r.min_price) if r.min_price else None,
            "max_price": float(r.max_price) if r.max_price else None,
            "data_tier": r.data_tier,
        }
        for r in rows
    ]


def _demo_records(mandi_name: str, crop_name: str, days: int) -> list[dict]:
    from app.demo_data import get_demo_prices_for_mandi_crop
    demo_recs = get_demo_prices_for_mandi_crop(mandi_name, crop_name, days)
    return [
        {
            "date": datetime.strptime(r["arrival_date"], "%d/%m/%Y").date().isoformat(),
            "modal_price": float(r["modal_price"]),
            "min_price": float(r.get("min_price", 0) or 0),
            "max_price": float(r.get("max_price", 0) or 0),
            "data_tier": "DEMO",
        }
        for r in demo_recs
    ]


async def _resolve_mandi_series(
    db: AsyncSession,
    mandi_id: int,
    mandi_name: str,
    mandi_district: str,
    mandi_state: str,
    canonical_crop_id: int,
    crop_name: str,
    cutoff: date,
    days: int,
) -> tuple[list[dict], str]:
    """
    Returns (data_list, used_tier) for a single mandi using the 3-tier strategy.
    Isolated so it can be called concurrently via asyncio.gather.
    """
    from app.agents.price_fetch_agent import _fetch_from_agmarknet, _upsert_price_records

    # ── Tier 1: DB cache, fresh ────────────────────────────────────────────────
    cached_rows = await _get_cached_records(db, mandi_id, canonical_crop_id, cutoff)
    live_rows = [r for r in cached_rows if getattr(r, 'data_tier', 'LIVE') != 'DEMO']

    if live_rows and _is_cache_fresh(live_rows):
        logger.info(f"CACHE HIT: {mandi_name} — {len(live_rows)} rows (skip API)")
        return _rows_to_data(live_rows), "LIVE"

    # ── Tier 2: Live Agmarknet API ─────────────────────────────────────────────
    try:
        api_records = await _fetch_from_agmarknet(
            state=mandi_state,
            district=mandi_district,
            commodity=crop_name,
            days_back=days,
        )
        # Filter to this specific mandi's market (flexible name matching)
        mandi_records = [
            r for r in api_records
            if r["market"].lower().strip() in mandi_name.lower()
            or mandi_name.lower().split()[0] in r["market"].lower()
        ]
        if mandi_records:
            await _upsert_price_records(db, mandi_records, mandi_id, canonical_crop_id)
            # Commit so cache is updated for next request
            try:
                await db.commit()
            except Exception:
                await db.rollback()
            logger.info(f"LIVE: {mandi_name} — {len(mandi_records)} records fetched & cached")
            return [
                {
                    "date": (
                        r["arrival_date"].isoformat()
                        if isinstance(r["arrival_date"], date)
                        else r["arrival_date"]
                    ),
                    "modal_price": float(r["modal_price"]),
                    "min_price": float(r.get("min_price", 0) or 0),
                    "max_price": float(r.get("max_price", 0) or 0),
                    "data_tier": "LIVE",
                }
                for r in mandi_records
            ], "LIVE"

        # API succeeded but returned nothing for this specific mandi
        if live_rows:
            logger.info(f"API empty → stale cache: {mandi_name}")
            return _rows_to_data(live_rows), "CACHE_STALE"

        # Nothing at all from API or cache — use demo
        logger.warning(f"API empty, no cache → DEMO: {mandi_name}")
        return _demo_records(mandi_name, crop_name, days), "DEMO"

    except Exception as e:
        # ── Tier 3: Demo fallback (API truly failed) ───────────────────────────
        if live_rows:
            logger.warning(f"API failed ({e}), stale cache: {mandi_name}")
            return _rows_to_data(live_rows), "CACHE_STALE"
        logger.warning(f"DEMO FALLBACK: {mandi_name} / {crop_name} — {e}")
        return _demo_records(mandi_name, crop_name, days), "DEMO"


async def get_price_history(
    db: AsyncSession,
    canonical_crop_id: int,
    mandi_ids: list[int] | None = None,
    days: int = 30,
    state: str | None = None,
) -> dict:
    """
    Returns structured price history for chart rendering.

    Resolution per mandi (Tier 1 → 2 → 3):
      1. DB cache fresh (< 6h) → instant, zero API overhead
      2. Live Agmarknet HTTP API → upsert cache → return LIVE
      3. Demo fallback ONLY on API failure
    All mandis resolved concurrently (asyncio.gather) to avoid Vercel timeout.
    """
    cutoff = date.today() - timedelta(days=days)

    # ── Resolve mandi IDs from state ──────────────────────────────────────────
    resolved_state = 'Madhya Pradesh'
    if state and not mandi_ids:
        state_key = next(
            (st for st in STATE_ALL_MANDIS
             if st.lower() in state.lower() or state.lower() in st.lower()),
            'Madhya Pradesh'
        )
        mandi_ids = [m['id'] for m in STATE_ALL_MANDIS[state_key]]
        resolved_state = state_key
    elif state:
        resolved_state = state
    if not mandi_ids:
        mandi_ids = [1, 2, 3, 4, 21, 22]

    # ── Fetch crop info ────────────────────────────────────────────────────────
    crop_row = (await db.get(CropCanon, canonical_crop_id)) if db else None
    crop_ref = {
        "id":             crop_row.id              if crop_row else canonical_crop_id,
        "canonical_name": crop_row.canonical_name  if crop_row else "Wheat",
        "variety":        crop_row.variety         if crop_row else None,
        "is_perishable":  crop_row.is_perishable   if crop_row else False,
        "shelf_life_days":crop_row.shelf_life_days if crop_row else 180,
        "aliases":        crop_row.get_aliases()   if crop_row else [],
    }
    crop_name = crop_ref["canonical_name"]

    # ── Resolve mandi metadata ─────────────────────────────────────────────────
    async def _get_mandi_meta(mandi_id: int) -> dict:
        info = FLAT_MANDI_LOOKUP.get(mandi_id)
        if info:
            return info
        if db:
            m_row = await db.get(Mandi, mandi_id)
            if m_row:
                return {'id': mandi_id, 'name': m_row.name,
                        'district': m_row.district, 'state': m_row.state}
        return {'id': mandi_id, 'name': f"Mandi {mandi_id}",
                'district': resolved_state.split()[0], 'state': resolved_state}

    mandi_metas = {mid: await _get_mandi_meta(mid) for mid in mandi_ids}

    # ── Concurrent 3-tier resolution for all mandis ────────────────────────────
    tier_priority = {"LIVE": 0, "CACHE": 1, "CACHE_STALE": 2, "DEMO": 3}
    overall_tier = "LIVE"
    ma7_series: dict[int, list] = {}
    ma30_series: dict[int, list] = {}
    series_out = []

    if db:
        tasks = [
            _resolve_mandi_series(
                db,
                mid,
                mandi_metas[mid]['name'],
                mandi_metas[mid]['district'],
                mandi_metas[mid]['state'],
                canonical_crop_id,
                crop_name,
                cutoff,
                days,
            )
            for mid in mandi_ids
        ]
        # BUG FIX: return_exceptions=True so one mandi failure doesn't kill all others
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        results = [
            (_demo_records(mandi_metas[mid]['name'], crop_name, days), "DEMO")
            for mid in mandi_ids
        ]

    for mid, result in zip(mandi_ids, results):
        meta = mandi_metas[mid]
        mandi_name = meta['name']

        if isinstance(result, Exception):
            logger.error(f"Unhandled error for {mandi_name}: {result}")
            data, used_tier = _demo_records(mandi_name, crop_name, days), "DEMO"
        else:
            data, used_tier = result

        # ── MA computation ─────────────────────────────────────────────────────
        price_tuples = sorted(
            [(date.fromisoformat(r["date"]), r["modal_price"]) for r in data if r.get("modal_price")],
            key=lambda x: x[0]
        )
        ma7_series[mid]  = _compute_moving_average(price_tuples, 7)
        ma30_series[mid] = _compute_moving_average(price_tuples, 30)

        # Completeness (BUG FIX: guard days=0)
        actual_days = len({r["date"] for r in data})
        completeness = round(actual_days / days * 100, 1) if days > 0 else 0.0

        # Track worst tier
        if tier_priority.get(used_tier, 0) > tier_priority.get(overall_tier, 0):
            overall_tier = used_tier

        series_out.append({
            "mandi_id":             mid,
            "mandi_name":           mandi_name,
            "data":                 data,
            "data_completeness_pct": completeness,
            "data_tier":            used_tier,
        })

    return {
        "crop":              crop_ref,
        "series":            series_out,
        "ma7_series":        ma7_series,
        "ma30_series":       ma30_series,
        "overall_data_tier": overall_tier,
    }
