"""
app/demo_data.py
─────────────────────────────────────────────────────────
Realistic static demo price dataset for resilient fallback.
Covers 5 states × 3 mandis × 8 crops × 30 days.
Flagged clearly as DEMO in every response.
"""

from datetime import date, timedelta
import random

random.seed(42)  # Deterministic demo data

# ─── Mandi seed data ─────────────────────────────────────────────────────────
DEMO_MANDIS = [
    # Madhya Pradesh
    {"id": 1, "name": "Ujjain", "state": "Madhya Pradesh", "district": "Ujjain", "latitude": 23.1828, "longitude": 75.7772, "apmc_code": "MP_UJN"},
    {"id": 2, "name": "Indore", "state": "Madhya Pradesh", "district": "Indore", "latitude": 22.7196, "longitude": 75.8577, "apmc_code": "MP_IDR"},
    {"id": 3, "name": "Dewas", "state": "Madhya Pradesh", "district": "Dewas", "latitude": 22.9623, "longitude": 76.0525, "apmc_code": "MP_DWS"},
    # Rajasthan
    {"id": 4, "name": "Jaipur Muhana", "state": "Rajasthan", "district": "Jaipur", "latitude": 26.7606, "longitude": 75.9024, "apmc_code": "RJ_JPR"},
    {"id": 5, "name": "Kota", "state": "Rajasthan", "district": "Kota", "latitude": 25.2138, "longitude": 75.8648, "apmc_code": "RJ_KOT"},
    {"id": 6, "name": "Ajmer", "state": "Rajasthan", "district": "Ajmer", "latitude": 26.4499, "longitude": 74.6399, "apmc_code": "RJ_AJM"},
    # Maharashtra
    {"id": 7, "name": "Pune Apmc", "state": "Maharashtra", "district": "Pune", "latitude": 18.5204, "longitude": 73.8567, "apmc_code": "MH_PUN"},
    {"id": 8, "name": "Nashik", "state": "Maharashtra", "district": "Nashik", "latitude": 19.9975, "longitude": 73.7898, "apmc_code": "MH_NSK"},
    {"id": 9, "name": "Aurangabad", "state": "Maharashtra", "district": "Aurangabad", "latitude": 19.8762, "longitude": 75.3433, "apmc_code": "MH_AUR"},
    # Punjab
    {"id": 10, "name": "Ludhiana", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9010, "longitude": 75.8573, "apmc_code": "PB_LDH"},
    {"id": 11, "name": "Amritsar", "state": "Punjab", "district": "Amritsar", "latitude": 31.6340, "longitude": 74.8723, "apmc_code": "PB_ASR"},
    {"id": 12, "name": "Jalandhar", "state": "Punjab", "district": "Jalandhar", "latitude": 31.3260, "longitude": 75.5762, "apmc_code": "PB_JLD"},
    # Uttar Pradesh
    {"id": 13, "name": "Agra", "state": "Uttar Pradesh", "district": "Agra", "latitude": 27.1767, "longitude": 78.0081, "apmc_code": "UP_AGR"},
    {"id": 14, "name": "Kanpur", "state": "Uttar Pradesh", "district": "Kanpur", "latitude": 26.4499, "longitude": 80.3319, "apmc_code": "UP_KNP"},
    {"id": 15, "name": "Varanasi", "state": "Uttar Pradesh", "district": "Varanasi", "latitude": 25.3176, "longitude": 82.9739, "apmc_code": "UP_VNS"},
]

# ─── Crop base prices (₹/quintal) ────────────────────────────────────────────
DEMO_CROP_PRICES = {
    "Wheat":     {"base": 2300, "volatility": 80,   "trend": 0.8},  # Slight uptrend
    "Mustard":   {"base": 4800, "volatility": 150,  "trend": 1.2},  # Rising
    "Gram":      {"base": 5200, "volatility": 200,  "trend": -0.5}, # Slight drop
    "Soybean":   {"base": 4100, "volatility": 120,  "trend": 0.0},  # Stable
    "Onion":     {"base": 1500, "volatility": 400,  "trend": 2.5},  # Very volatile, rising
    "Tomato":    {"base": 2000, "volatility": 600,  "trend": -3.0}, # Falling
    "Potato":    {"base": 900,  "volatility": 100,  "trend": 0.3},  # Stable
    "Cotton":    {"base": 6500, "volatility": 200,  "trend": 0.5},  # Slightly rising
}

# Mandi-specific price offsets (₹/quintal vs base)
MANDI_OFFSETS = {
    1: 0,    # Ujjain — baseline
    2: 210,  # Indore — premium market
    3: -50,  # Dewas — slightly lower
    4: 150,  # Jaipur — premium
    5: -80,  # Kota — lower
    6: 100,  # Ajmer — moderate
    7: 300,  # Pune — high
    8: 200,  # Nashik — high
    9: 50,   # Aurangabad — moderate
    10: 180, # Ludhiana — premium wheat market
    11: 160, # Amritsar
    12: 140, # Jalandhar
    13: -30, # Agra
    14: 20,  # Kanpur
    15: -60, # Varanasi
}


def _generate_price_series(crop_name: str, mandi_id: int, days: int = 30) -> list[dict]:
    """Generate deterministic realistic price series for demo purposes."""
    crop = DEMO_CROP_PRICES.get(crop_name, {"base": 2000, "volatility": 100, "trend": 0})
    base = crop["base"] + MANDI_OFFSETS.get(mandi_id, 0)
    vol = crop["volatility"]
    trend_per_day = crop["trend"]

    today = date.today()
    records = []
    rng = random.Random(hash(f"{crop_name}_{mandi_id}") % (2**31))

    for i in range(days):
        day = today - timedelta(days=(days - 1 - i))
        trend_effect = trend_per_day * i
        noise = rng.uniform(-vol, vol)
        modal = max(100, round(base + trend_effect + noise, 0))
        records.append({
            "arrival_date": day.strftime("%d/%m/%Y"),
            "state": next((m["state"] for m in DEMO_MANDIS if m["id"] == mandi_id), ""),
            "district": next((m["district"] for m in DEMO_MANDIS if m["id"] == mandi_id), ""),
            "market": next((m["name"] for m in DEMO_MANDIS if m["id"] == mandi_id), ""),
            "commodity": crop_name,
            "variety": crop_name,
            "grade": "FAQ",
            "min_price": float(max(100, modal - vol * 0.3)),
            "max_price": float(modal + vol * 0.3),
            "modal_price": float(modal),
            "data_tier": "DEMO",
        })
    return records


def get_demo_prices_for_mandi_crop(mandi_name: str, crop_canonical_name: str, days: int = 30) -> list[dict]:
    """Get demo price records for a specific mandi and crop."""
    # Find mandi_id from name
    mandi = next((m for m in DEMO_MANDIS if m["name"].lower() == mandi_name.lower()), None)
    if not mandi:
        # Closest name match fallback
        mandi = DEMO_MANDIS[0]
    return _generate_price_series(crop_canonical_name, mandi["id"], days)


def get_all_demo_mandis_for_state(state: str) -> list[dict]:
    """Get all demo mandis for a given state."""
    return [m for m in DEMO_MANDIS if m["state"].lower() == state.lower()]


DEMO_DATA_BANNER = (
    "🔴 DEMO DATA — Prices shown are NOT real-time. "
    "They are illustrative only. Register a free API key at "
    "data.gov.in to see live Agmarknet prices."
)
