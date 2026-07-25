"""
app/agents/history_agent.py
─────────────────────────────────────────────────────────
Agent 8: Returns structured price history for chart rendering.
Pre-computes MA7 and MA30 series server-side.
"""

import logging
from datetime import date, timedelta, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceRecord, CropCanon, Mandi

logger = logging.getLogger(__name__)


def _compute_moving_average(
    prices: list[tuple[date, float]], window: int
) -> list[dict]:
    """Compute a moving average series of `window` days."""
    result = []
    values = []
    for i, (d, price) in enumerate(prices):
        values.append(price)
        window_values = values[-window:] if len(values) >= window else values
        result.append({"date": d.isoformat(), "value": round(sum(window_values) / len(window_values), 2)})
    return result


async def get_price_history(
    db: AsyncSession,
    canonical_crop_id: int,
    mandi_ids: list[int] = None,
    days: int = 30,
    state: str = None,
) -> dict:
    """
    Returns price series for all requested mandis + pre-computed MA7/MA30.
    Dynamically fetches all mandis belonging to state if state parameter is supplied.
    """
    cutoff = date.today() - timedelta(days=days)

    # Map states to their full set of APMC Mandi districts
    STATE_ALL_MANDIS = {
        'Madhya Pradesh': [
            {'id': 1, 'name': 'Ujjain APMC'}, {'id': 2, 'name': 'Dewas Mandi'},
            {'id': 3, 'name': 'Indore Mandi'}, {'id': 4, 'name': 'Bhopal APMC'},
            {'id': 21, 'name': 'Gwalior Mandi'}, {'id': 22, 'name': 'Jabalpur APMC'},
            {'id': 23, 'name': 'Mandsaur Mandi'}, {'id': 24, 'name': 'Ratlam APMC'}
        ],
        'Maharashtra': [
            {'id': 5, 'name': 'Nashik APMC'}, {'id': 6, 'name': 'Pune Mandi'},
            {'id': 7, 'name': 'Nagpur APMC'}, {'id': 8, 'name': 'Aurangabad Mandi'},
            {'id': 25, 'name': 'Amravati APMC'}, {'id': 26, 'name': 'Solapur Mandi'},
            {'id': 27, 'name': 'Kolhapur APMC'}, {'id': 28, 'name': 'Latur Mandi'}
        ],
        'Punjab': [
            {'id': 9, 'name': 'Ludhiana APMC'}, {'id': 10, 'name': 'Amritsar Mandi'},
            {'id': 11, 'name': 'Jalandhar APMC'}, {'id': 12, 'name': 'Patiala Mandi'},
            {'id': 29, 'name': 'Bathinda APMC'}, {'id': 30, 'name': 'Sangrur Mandi'}
        ],
        'Haryana': [
            {'id': 13, 'name': 'Karnal APMC'}, {'id': 14, 'name': 'Ambala Mandi'},
            {'id': 15, 'name': 'Hisar APMC'}, {'id': 16, 'name': 'Rohtak Mandi'},
            {'id': 31, 'name': 'Sirsa APMC'}, {'id': 32, 'name': 'Panipat Mandi'}
        ],
        'Uttar Pradesh': [
            {'id': 17, 'name': 'Agra APMC'}, {'id': 18, 'name': 'Kanpur Mandi'},
            {'id': 19, 'name': 'Varanasi APMC'}, {'id': 20, 'name': 'Lucknow Mandi'},
            {'id': 33, 'name': 'Aligarh APMC'}, {'id': 34, 'name': 'Bareilly Mandi'}
        ]
    }

    # ── Resolve mandi IDs from state if mandi_ids is not supplied ────────
    if state and not mandi_ids:
        state_key = next((st for st in STATE_ALL_MANDIS if st.lower() in state.lower() or state.lower() in st.lower()), 'Madhya Pradesh')
        all_st_mandis = STATE_ALL_MANDIS[state_key]
        mandi_ids = [m['id'] for m in all_st_mandis]
    if not mandi_ids:
        mandi_ids = [1, 2, 3, 4, 21, 22]

    # ── Fetch crop info ───────────────────────────────────────────────────
    crop_row = await db.get(CropCanon, canonical_crop_id) if db else None
    crop_ref = {
        "id": crop_row.id if crop_row else canonical_crop_id,
        "canonical_name": crop_row.canonical_name if crop_row else ("Wheat" if canonical_crop_id == 1 else "Soybean"),
        "variety": crop_row.variety if crop_row else "Sharbati",
        "is_perishable": crop_row.is_perishable if crop_row else False,
        "shelf_life_days": crop_row.shelf_life_days if crop_row else 180,
        "aliases": crop_row.get_aliases() if crop_row else [],
    }

    # ── Fetch price records ───────────────────────────────────────────────
    rows = []
    if db:
        result = await db.execute(
            select(PriceRecord, Mandi.name)
            .join(Mandi, PriceRecord.mandi_id == Mandi.id)
            .where(
                PriceRecord.canonical_crop_id == canonical_crop_id,
                PriceRecord.mandi_id.in_(mandi_ids),
                PriceRecord.arrival_date >= cutoff,
            )
            .order_by(PriceRecord.arrival_date.asc())
        )
        rows = result.all()

    # ── Group by mandi ────────────────────────────────────────────────────
    series_map: dict[int, list] = {mid: [] for mid in mandi_ids}
    mandi_names: dict[int, str] = {}

    for row in rows:
        pr = row[0]
        mandi_name = row[1]
        series_map.setdefault(pr.mandi_id, []).append({
            "date": pr.arrival_date.isoformat(),
            "modal_price": float(pr.modal_price),
            "min_price": float(pr.min_price) if pr.min_price else None,
            "max_price": float(pr.max_price) if pr.max_price else None,
            "data_tier": pr.data_tier,
        })
        mandi_names[pr.mandi_id] = mandi_name

    # ── Compute MA series ─────────────────────────────────────────────────
    ma7_series: dict[int, list] = {}
    ma30_series: dict[int, list] = {}
    series_out = []

    overall_tier = "LIVE"
    tier_priority = {"LIVE": 0, "CACHE": 1, "CACHE_STALE": 2, "DEMO": 3}

    for mandi_id in mandi_ids:
        data = series_map.get(mandi_id, [])
        
        # Fetch Mandi name if missing
        if mandi_id not in mandi_names:
            m_row = await db.get(Mandi, mandi_id) if db else None
            if m_row:
                mandi_name = m_row.name
            else:
                flat_mandis = [m for st_list in STATE_ALL_MANDIS.values() for m in st_list]
                found_m = next((m for m in flat_mandis if m['id'] == mandi_id), None)
                mandi_name = found_m['name'] if found_m else f"Mandi {mandi_id}"
            mandi_names[mandi_id] = mandi_name
        else:
            mandi_name = mandi_names[mandi_id]

        # Auto-populate historical series if database has no records yet (e.g. fresh first run)
        if not data:
            from app.demo_data import get_demo_prices_for_mandi_crop
            demo_recs = get_demo_prices_for_mandi_crop(mandi_name, crop_ref["canonical_name"], days)
            data = [
                {
                    "date": datetime.strptime(r["arrival_date"], "%d/%m/%Y").date().isoformat(),
                    "modal_price": float(r["modal_price"]),
                    "min_price": float(r.get("min_price", 0) or 0),
                    "max_price": float(r.get("max_price", 0) or 0),
                    "data_tier": "DEMO",
                }
                for r in demo_recs
            ]

        price_tuples = [
            (date.fromisoformat(r["date"]), r["modal_price"])
            for r in data if r.get("modal_price")
        ]
        price_tuples.sort(key=lambda x: x[0])

        ma7_series[mandi_id] = _compute_moving_average(price_tuples, 7)
        ma30_series[mandi_id] = _compute_moving_average(price_tuples, 30)

        # Completeness
        expected_days = days
        actual_days = len(set(r["date"] for r in data))
        completeness = round((actual_days / expected_days) * 100, 1) if expected_days > 0 else 0

        # Worst tier
        for r in data:
            t = r.get("data_tier", "LIVE")
            if tier_priority.get(t, 0) > tier_priority.get(overall_tier, 0):
                overall_tier = t

        series_out.append({
            "mandi_id": mandi_id,
            "mandi_name": mandi_name,
            "data": data,
            "data_completeness_pct": completeness,
        })

    return {
        "crop": crop_ref,
        "series": series_out,
        "ma7_series": ma7_series,
        "ma30_series": ma30_series,
        "overall_data_tier": overall_tier,
    }
