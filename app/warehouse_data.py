"""
app/warehouse_data.py
─────────────────────────────────────────────────────────
Comprehensive seed & demo data for WDRA-registered Warehouses,
Cold Storages, and Grain Silos across 5 major agricultural states in India:
  1. Madhya Pradesh
  2. Maharashtra
  3. Punjab
  4. Haryana
  5. Uttar Pradesh

Includes accurate real-world latitude/longitude coordinates strictly within
state boundaries, total capacity (MT), available space, daily storage fees (₹/qtl/day),
and supported crop types. Ready for distribution, route optimization, and multi-crop planning.
"""

from typing import TypedDict, List

class WarehouseRecord(TypedDict):
    id: int
    name: str
    warehouse_type: str  # DRY_SILO | COLD_STORAGE | MULTI_COMMODITY
    state: str
    district: str
    latitude: float
    longitude: float
    total_capacity_mt: float
    available_capacity_mt: float
    daily_fee_per_qtl: float
    wdra_registered: bool
    temperature_controlled: bool
    supported_crops: List[str]

WAREHOUSES_DATA: List[WarehouseRecord] = [
    # ── MADHYA PRADESH ──────────────────────────────────────────────────────────
    {
        "id": 101,
        "name": "CWC Ujjain Central Logistics Hub",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Madhya Pradesh",
        "district": "Ujjain",
        "latitude": 23.1765,
        "longitude": 75.7885,
        "total_capacity_mt": 35000.0,
        "available_capacity_mt": 12400.0,
        "daily_fee_per_qtl": 0.25,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Soybean", "Gram", "Mustard"]
    },
    {
        "id": 102,
        "name": "MPWLC Dewas Steel Grain Silo",
        "warehouse_type": "DRY_SILO",
        "state": "Madhya Pradesh",
        "district": "Dewas",
        "latitude": 22.9676,
        "longitude": 76.0534,
        "total_capacity_mt": 50000.0,
        "available_capacity_mt": 21500.0,
        "daily_fee_per_qtl": 0.20,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Soybean", "Maize"]
    },
    {
        "id": 103,
        "name": "Indore Cold Chain & Agro Storage",
        "warehouse_type": "COLD_STORAGE",
        "state": "Madhya Pradesh",
        "district": "Indore",
        "latitude": 22.7196,
        "longitude": 75.8577,
        "total_capacity_mt": 18000.0,
        "available_capacity_mt": 5200.0,
        "daily_fee_per_qtl": 0.65,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Potato", "Onion", "Garlic", "Tomato"]
    },
    {
        "id": 104,
        "name": "MPWLC Bhopal Regional Grain Repository",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Madhya Pradesh",
        "district": "Bhopal",
        "latitude": 23.2599,
        "longitude": 77.4126,
        "total_capacity_mt": 40000.0,
        "available_capacity_mt": 14800.0,
        "daily_fee_per_qtl": 0.24,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Gram", "Soybean"]
    },
    {
        "id": 105,
        "name": "Gwalior Agro Cold Logistics",
        "warehouse_type": "COLD_STORAGE",
        "state": "Madhya Pradesh",
        "district": "Gwalior",
        "latitude": 26.2183,
        "longitude": 78.1828,
        "total_capacity_mt": 15000.0,
        "available_capacity_mt": 4100.0,
        "daily_fee_per_qtl": 0.60,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Potato", "Onion", "Mustard"]
    },
    {
        "id": 106,
        "name": "Jabalpur Mahakoshal Warehouse",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Madhya Pradesh",
        "district": "Jabalpur",
        "latitude": 23.1815,
        "longitude": 79.9864,
        "total_capacity_mt": 28000.0,
        "available_capacity_mt": 9600.0,
        "daily_fee_per_qtl": 0.22,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Paddy", "Wheat", "Gram"]
    },

    # ── MAHARASHTRA ─────────────────────────────────────────────────────────────
    {
        "id": 201,
        "name": "Nashik Agro Cold Storage & Export Hub",
        "warehouse_type": "COLD_STORAGE",
        "state": "Maharashtra",
        "district": "Nashik",
        "latitude": 19.9975,
        "longitude": 73.7898,
        "total_capacity_mt": 25000.0,
        "available_capacity_mt": 7800.0,
        "daily_fee_per_qtl": 0.70,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Onion", "Grapes", "Pomegranate", "Tomato"]
    },
    {
        "id": 202,
        "name": "MSWC Pune Logistics & Grain Park",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Maharashtra",
        "district": "Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "total_capacity_mt": 45000.0,
        "available_capacity_mt": 18200.0,
        "daily_fee_per_qtl": 0.28,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Maize", "Soybean"]
    },
    {
        "id": 203,
        "name": "Aurangabad Marathwada Grain Silos",
        "warehouse_type": "DRY_SILO",
        "state": "Maharashtra",
        "district": "Aurangabad",
        "latitude": 19.8762,
        "longitude": 75.3433,
        "total_capacity_mt": 30000.0,
        "available_capacity_mt": 11000.0,
        "daily_fee_per_qtl": 0.23,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Cotton", "Soybean", "Jowar", "Bajra"]
    },
    {
        "id": 204,
        "name": "Nagpur Vidarbha Central Warehouse",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Maharashtra",
        "district": "Nagpur",
        "latitude": 21.1458,
        "longitude": 79.0882,
        "total_capacity_mt": 50000.0,
        "available_capacity_mt": 19500.0,
        "daily_fee_per_qtl": 0.26,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Cotton", "Soybean", "Paddy", "Orange"]
    },

    # ── PUNJAB ──────────────────────────────────────────────────────────────────
    {
        "id": 301,
        "name": "PUNGRAIN Ludhiana Modern Steel Silo",
        "warehouse_type": "DRY_SILO",
        "state": "Punjab",
        "district": "Ludhiana",
        "latitude": 30.9010,
        "longitude": 75.8573,
        "total_capacity_mt": 75000.0,
        "available_capacity_mt": 32000.0,
        "daily_fee_per_qtl": 0.18,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Maize"]
    },
    {
        "id": 302,
        "name": "CWC Amritsar Border Logistics Yard",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Punjab",
        "district": "Amritsar",
        "latitude": 31.6340,
        "longitude": 74.8723,
        "total_capacity_mt": 40000.0,
        "available_capacity_mt": 15400.0,
        "daily_fee_per_qtl": 0.22,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Basmati Rice"]
    },
    {
        "id": 303,
        "name": "Jalandhar Cold Storage Complex",
        "warehouse_type": "COLD_STORAGE",
        "state": "Punjab",
        "district": "Jalandhar",
        "latitude": 31.3260,
        "longitude": 75.5762,
        "total_capacity_mt": 22000.0,
        "available_capacity_mt": 6100.0,
        "daily_fee_per_qtl": 0.58,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Potato", "Vegetables", "Fruits"]
    },

    # ── HARYANA ─────────────────────────────────────────────────────────────────
    {
        "id": 401,
        "name": "HAFED Karnal Grain Storage Silo",
        "warehouse_type": "DRY_SILO",
        "state": "Haryana",
        "district": "Karnal",
        "latitude": 29.6857,
        "longitude": 76.9905,
        "total_capacity_mt": 60000.0,
        "available_capacity_mt": 24000.0,
        "daily_fee_per_qtl": 0.19,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Paddy", "Wheat", "Basmati Rice"]
    },
    {
        "id": 402,
        "name": "SWC Hisar Agricultural Warehouse",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Haryana",
        "district": "Hisar",
        "latitude": 29.1492,
        "longitude": 75.7217,
        "total_capacity_mt": 35000.0,
        "available_capacity_mt": 11800.0,
        "daily_fee_per_qtl": 0.21,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Mustard", "Cotton", "Wheat", "Gram"]
    },
    {
        "id": 403,
        "name": "Ambala Cold Logistics Yard",
        "warehouse_type": "COLD_STORAGE",
        "state": "Haryana",
        "district": "Ambala",
        "latitude": 30.3782,
        "longitude": 76.7767,
        "total_capacity_mt": 16000.0,
        "available_capacity_mt": 4900.0,
        "daily_fee_per_qtl": 0.55,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Potato", "Onion", "Tomato"]
    },

    # ── UTTAR PRADESH ───────────────────────────────────────────────────────────
    {
        "id": 501,
        "name": "Agra Potato Cold Chain & Storage Hub",
        "warehouse_type": "COLD_STORAGE",
        "state": "Uttar Pradesh",
        "district": "Agra",
        "latitude": 27.1767,
        "longitude": 78.0081,
        "total_capacity_mt": 65000.0,
        "available_capacity_mt": 21000.0,
        "daily_fee_per_qtl": 0.52,
        "wdra_registered": True,
        "temperature_controlled": True,
        "supported_crops": ["Potato", "Onion", "Garlic"]
    },
    {
        "id": 502,
        "name": "UPSWC Kanpur Central Grain Terminal",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Uttar Pradesh",
        "district": "Kanpur",
        "latitude": 26.4499,
        "longitude": 80.3319,
        "total_capacity_mt": 55000.0,
        "available_capacity_mt": 19000.0,
        "daily_fee_per_qtl": 0.23,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Mustard", "Gram"]
    },
    {
        "id": 503,
        "name": "Varanasi Eastern UP Logistics Park",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Uttar Pradesh",
        "district": "Varanasi",
        "latitude": 25.3176,
        "longitude": 82.9739,
        "total_capacity_mt": 38000.0,
        "available_capacity_mt": 13200.0,
        "daily_fee_per_qtl": 0.25,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Paddy", "Wheat", "Vegetables"]
    },
    {
        "id": 504,
        "name": "Lucknow Regional Storage Repository",
        "warehouse_type": "MULTI_COMMODITY",
        "state": "Uttar Pradesh",
        "district": "Lucknow",
        "latitude": 26.8467,
        "longitude": 80.9462,
        "total_capacity_mt": 42000.0,
        "available_capacity_mt": 16500.0,
        "daily_fee_per_qtl": 0.24,
        "wdra_registered": True,
        "temperature_controlled": False,
        "supported_crops": ["Wheat", "Paddy", "Pulse"]
    }
]


def get_warehouses(
    state: str | None = None,
    district: str | None = None,
    crop_name: str | None = None,
    is_cold_storage: bool | None = None,
) -> List[WarehouseRecord]:
    """
    Filter warehouses by state, district, crop type, or cold storage capability.
    """
    result = WAREHOUSES_DATA
    if state:
        result = [w for w in result if w["state"].lower().strip() == state.lower().strip()]
    if district:
        result = [w for w in result if w["district"].lower().strip() == district.lower().strip()]
    if crop_name:
        result = [
            w for w in result
            if any(c.lower().strip() in crop_name.lower().strip() or crop_name.lower().strip() in c.lower().strip() for c in w["supported_crops"])
        ]
    if is_cold_storage is not None:
        result = [w for w in result if w["temperature_controlled"] == is_cold_storage]
    return result
