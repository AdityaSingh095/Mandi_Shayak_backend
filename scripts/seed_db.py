"""
backend/scripts/seed_db.py
─────────────────────────────────────────────────────────
One-time seed script: populates mandis, crop_canon, and system_config tables.
Generates embeddings for crops (if fastembed available).
Run once before first use: python scripts/seed_db.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal, init_db
from app.models import CropCanon, SystemConfig
from app.demo_data import DEMO_MANDIS
from app.embeddings import embed_text, build_crop_embed_text


CROPS_TO_SEED = [
    ("Wheat",     "Sharbati",  False, None,  ["Gehun Sharbati", "Bansi", "MP Wheat"]),
    ("Wheat",     "Durum",     False, None,  ["Durum Gehun", "Kata"]),
    ("Wheat",     None,        False, None,  ["Gehun", "Gehu", "Kanak", "Wheat", "Safed Gehun"]),
    ("Mustard",   None,        False, None,  ["Sarson", "Rai", "Lahi", "Rape Seed", "Rapeseed"]),
    ("Mustard",   "Yellow",    False, None,  ["Peeli Sarson", "Yellow Sarson"]),
    ("Gram",      "Desi",      False, None,  ["Chana", "Kala Chana", "Desi Chana", "Bengal Gram"]),
    ("Gram",      "Kabuli",    False, None,  ["Kabuli Chana", "Chickpea", "White Chana"]),
    ("Soybean",   None,        False, None,  ["Soya Bean", "Soyabean", "Soya"]),
    ("Maize",     None,        False, None,  ["Makka", "Makki", "Corn"]),
    ("Paddy",     "Common",    False, None,  ["Dhan", "Chawal", "Rice Paddy"]),
    ("Cotton",    None,        False, None,  ["Kapas", "Rui", "Cotton Seed"]),
    ("Onion",     "Red",       True,  14,    ["Pyaaz", "Kanda", "Red Onion", "Pyaz"]),
    ("Onion",     "White",     True,  14,    ["Safed Pyaaz", "White Onion"]),
    ("Tomato",    None,        True,  7,     ["Tamatar", "Tamato"]),
    ("Potato",    None,        True,  60,    ["Aalu", "Aalo", "Batata"]),
    ("Sugarcane", None,        False, None,  ["Ganna", "Ikh"]),
    ("Bajra",     None,        False, None,  ["Pearl Millet"]),
    ("Jowar",     None,        False, None,  ["Sorghum", "Jwari"]),
    ("Groundnut", None,        False, None,  ["Moongphali", "Peanut"]),
    ("Sunflower", None,        False, None,  ["Surajmukhi"]),
]

SYSTEM_CONFIG_SEED = [
    ("trend.rising_threshold_pct",          "2.5",   "Min % MA7 vs MA30 to classify RISING"),
    ("trend.falling_threshold_pct",         "-2.5",  "Max % MA7 vs MA30 to classify FALLING"),
    ("trend.volatility_threshold_ratio",    "0.05",  "StdDev/MA7 ratio to flag volatile"),
    ("trend.min_days_for_analysis",         "7",     "Min days of data needed for trend"),
    ("trend.gap_interpolation_max_days",    "2",     "Max consecutive gaps to interpolate"),
    ("arbitrage.min_worthwhile_gain_inr",   "500",   "Min net gain (₹) for CONSIDER_TRAVEL"),
    ("arbitrage.strong_travel_gain_inr",    "1000",  "Net gain (₹) threshold for TRAVEL"),
    ("transport.default_own_vehicle_per_km","12",    "₹/km — own tractor/trolley"),
    ("transport.default_hired_per_km",      "20",    "₹/km — hired commercial vehicle"),
    ("cache.price_freshness_hours",         "6",     "Hours before cache triggers API refresh"),
    ("cache.stale_threshold_hours",         "48",    "Hours before cache is considered stale"),
    ("normalization.auto_resolve_threshold","0.85",  "Similarity score for auto-resolve"),
    ("normalization.confirm_threshold",     "0.75",  "Similarity score to show candidates"),
    ("normalization.reject_threshold",      "0.60",  "Below this score — UNRESOLVED"),
    ("retention.price_records_days",        "180",   "Delete price_records older than N days"),
    ("retention.audit_trail_days",          "90",    "Delete audit_trail older than N days"),
]


async def seed_data(db):
    from app.models import Mandi
    from sqlalchemy import select
    existing_mandis = (await db.execute(select(Mandi))).scalars().all()
    existing_names = {m.name for m in existing_mandis}
    added_mandis = 0
    for m in DEMO_MANDIS:
        if m["name"] not in existing_names:
            db.add(Mandi(
                name=m["name"],
                state=m["state"],
                district=m["district"],
                latitude=m["latitude"],
                longitude=m["longitude"],
                apmc_code=m.get("apmc_code"),
                is_active=True,
            ))
            added_mandis += 1
    await db.commit()

    import json
    existing_crops_q = await db.execute(select(CropCanon))
    existing_crops = existing_crops_q.scalars().all()
    existing_crop_keys = {(c.canonical_name, c.variety) for c in existing_crops}
    added_crops = 0

    for canonical_name, variety, is_perishable, shelf_life_days, aliases in CROPS_TO_SEED:
        if (canonical_name, variety) in existing_crop_keys:
            continue

        embed_text_str = build_crop_embed_text(canonical_name, variety, aliases)
        vector = embed_text(embed_text_str)

        crop = CropCanon(
            canonical_name=canonical_name,
            variety=variety,
            is_perishable=is_perishable,
            shelf_life_days=shelf_life_days,
            aliases_json=json.dumps(aliases),
            embedding_json=json.dumps(vector) if vector else None,
        )
        db.add(crop)
        added_crops += 1

    await db.commit()

    existing_cfg_q = await db.execute(select(SystemConfig))
    existing_cfg = {r.key for r in existing_cfg_q.scalars().all()}
    added_cfg = 0

    for key, value, description in SYSTEM_CONFIG_SEED:
        if key not in existing_cfg:
            db.add(SystemConfig(key=key, value=value, description=description, updated_by="seed_script"))
            added_cfg += 1

    await db.commit()


async def seed():
    print("Initializing DB tables...")
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_data(db)
    print("\n[OK] Seed complete! Run the server: uvicorn app.main:app --reload")


if __name__ == "__main__":
    asyncio.run(seed())
