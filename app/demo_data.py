"""
app/demo_data.py
─────────────────────────────────────────────────────────
Realistic static demo price dataset for resilient fallback.
Covers 5 states × 8 mandis × 8 crops × 30 days.
Flagged clearly as DEMO in every response.
"""

from datetime import date, timedelta
import random

# ─── Mandi seed data ─────────────────────────────────────────────────────────
DEMO_MANDIS = [
    # Madhya Pradesh
    {"id": 1,  "name": "Ujjain", "state": "Madhya Pradesh", "district": "Ujjain"},
    {"id": 2,  "name": "Dewas", "state": "Madhya Pradesh", "district": "Dewas"},
    {"id": 3,  "name": "Indore", "state": "Madhya Pradesh", "district": "Indore"},
    {"id": 4,  "name": "Bhopal", "state": "Madhya Pradesh", "district": "Bhopal"},
    {"id": 21, "name": "Gwalior", "state": "Madhya Pradesh", "district": "Gwalior"},
    {"id": 22, "name": "Jabalpur", "state": "Madhya Pradesh", "district": "Jabalpur"},
    {"id": 23, "name": "Mandsaur", "state": "Madhya Pradesh", "district": "Mandsaur"},
    {"id": 24, "name": "Ratlam", "state": "Madhya Pradesh", "district": "Ratlam"},

    # Maharashtra
    {"id": 5,  "name": "Nashik", "state": "Maharashtra", "district": "Nashik"},
    {"id": 6,  "name": "Pune", "state": "Maharashtra", "district": "Pune"},
    {"id": 7,  "name": "Nagpur", "state": "Maharashtra", "district": "Nagpur"},
    {"id": 8,  "name": "Aurangabad", "state": "Maharashtra", "district": "Aurangabad"},
    {"id": 25, "name": "Amravati", "state": "Maharashtra", "district": "Amravati"},
    {"id": 26, "name": "Solapur", "state": "Maharashtra", "district": "Solapur"},
    {"id": 27, "name": "Kolhapur", "state": "Maharashtra", "district": "Kolhapur"},
    {"id": 28, "name": "Latur", "state": "Maharashtra", "district": "Latur"},

    # Punjab
    {"id": 9,  "name": "Ludhiana", "state": "Punjab", "district": "Ludhiana"},
    {"id": 10, "name": "Amritsar", "state": "Punjab", "district": "Amritsar"},
    {"id": 11, "name": "Jalandhar", "state": "Punjab", "district": "Jalandhar"},
    {"id": 12, "name": "Patiala", "state": "Punjab", "district": "Patiala"},

    # Uttar Pradesh
    {"id": 13, "name": "Agra", "state": "Uttar Pradesh", "district": "Agra"},
    {"id": 14, "name": "Kanpur", "state": "Uttar Pradesh", "district": "Kanpur"},
    {"id": 15, "name": "Varanasi", "state": "Uttar Pradesh", "district": "Varanasi"},
    {"id": 16, "name": "Lucknow", "state": "Uttar Pradesh", "district": "Lucknow"},
]

# ─── Crop base prices (₹/quintal) ────────────────────────────────────────────
DEMO_CROP_PRICES = {
    "Wheat":     {"base": 2300, "volatility": 60,   "trend": 0.8},
    "Mustard":   {"base": 4800, "volatility": 120,  "trend": 1.2},
    "Gram":      {"base": 5200, "volatility": 150,  "trend": -0.5},
    "Soybean":   {"base": 4100, "volatility": 90,   "trend": 0.3},
    "Onion":     {"base": 1800, "volatility": 300,  "trend": 2.5},
    "Tomato":    {"base": 2200, "volatility": 400,  "trend": -2.0},
    "Potato":    {"base": 1100, "volatility": 80,   "trend": 0.4},
    "Cotton":    {"base": 6500, "volatility": 180,  "trend": 0.6},
    "Paddy":     {"base": 2180, "volatility": 50,   "trend": 0.5},
}

# Mandi-specific unique price offsets (₹/quintal vs base)
MANDI_OFFSETS = {
    1: 0,     # Ujjain APMC
    2: -45,   # Dewas Mandi
    3: 180,   # Indore Mandi
    4: 75,    # Bhopal APMC
    21: -90,  # Gwalior Mandi
    22: 110,  # Jabalpur APMC
    23: -130, # Mandsaur Mandi
    24: 40,   # Ratlam APMC

    5: 220,   # Nashik APMC
    6: 310,   # Pune Mandi
    7: 140,   # Nagpur APMC
    8: 60,    # Aurangabad Mandi
    25: -50,  # Amravati APMC
    26: 90,   # Solapur Mandi
    27: 170,  # Kolhapur APMC
    28: -30,  # Latur Mandi

    9: 250,   # Ludhiana APMC
    10: 190,  # Amritsar Mandi
    11: 150,  # Jalandhar
    12: 110,  # Patiala

    13: -80,  # Agra
    14: 30,   # Kanpur
    15: -40,  # Varanasi
    16: 95,   # Lucknow
}


def _generate_price_series(crop_name: str, mandi_id: int, days: int = 30) -> list[dict]:
    """Generate realistic distinct price series per mandi for demo purposes."""
    crop = DEMO_CROP_PRICES.get(crop_name, {"base": 2200, "volatility": 80, "trend": 0.5})
    base = crop["base"] + MANDI_OFFSETS.get(mandi_id, (mandi_id * 37) % 300 - 150)
    vol = crop["volatility"]
    trend_per_day = crop["trend"]

    today = date.today()
    records = []
    # Seed per crop + mandi_id so different mandis have distinct random walks
    rng = random.Random(hash(f"{crop_name}_{mandi_id}_v2") % (2**31))

    m_info = next((m for m in DEMO_MANDIS if m["id"] == mandi_id), {"name": f"Mandi {mandi_id}", "state": "", "district": ""})

    for i in range(days):
        day = today - timedelta(days=(days - 1 - i))
        trend_effect = trend_per_day * i
        # Sine-wave cycle + random noise to create distinct, realistic price curves
        sine_wave = math_sin(i * 0.4 + mandi_id) * (vol * 0.5)
        noise = rng.uniform(-vol * 0.5, vol * 0.5)
        modal = max(100, round(base + trend_effect + sine_wave + noise, 0))

        records.append({
            "arrival_date": day.strftime("%d/%m/%Y"),
            "state": m_info["state"],
            "district": m_info["district"],
            "market": m_info["name"],
            "commodity": crop_name,
            "variety": crop_name,
            "grade": "FAQ",
            "min_price": float(max(100, modal - vol * 0.25)),
            "max_price": float(modal + vol * 0.25),
            "modal_price": float(modal),
            "data_tier": "DEMO",
        })
    return records


def math_sin(x: float) -> float:
    import math
    return math.sin(x)


def get_demo_prices_for_mandi_crop(mandi_name: str, crop_canonical_name: str, days: int = 30) -> list[dict]:
    """Get distinct demo price records for a specific mandi and crop."""
    clean_name = mandi_name.lower().replace("apmc", "").replace("mandi", "").strip()

    # Substring search match so "Ujjain APMC" matches "Ujjain"
    mandi = next(
        (m for m in DEMO_MANDIS
         if m["name"].lower() in clean_name or clean_name in m["name"].lower()),
        None
    )

    if mandi:
        mandi_id = mandi["id"]
    else:
        # Assign unique deterministic ID based on mandi_name hash
        mandi_id = (abs(hash(mandi_name)) % 25) + 1

    return _generate_price_series(crop_canonical_name, mandi_id, days)


def get_all_demo_mandis_for_state(state: str) -> list[dict]:
    """Get all demo mandis for a given state."""
    return [m for m in DEMO_MANDIS if m["state"].lower() in state.lower() or state.lower() in m["state"].lower()]


DEMO_DATA_BANNER = "🔴 DEMO DATA — Illustrative price trajectories."
