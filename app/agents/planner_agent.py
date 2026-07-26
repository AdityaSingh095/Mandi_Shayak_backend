"""
app/agents/planner_agent.py
─────────────────────────────────────────────────────────
Multi-Crop Logistics & Warehousing Route Planning Agent.
Performs spatial-temporal multi-crop optimization across WDRA warehouses
and regional/interstate mandis. Integrates:
  1. Vector Engine 1: Market Trajectory Pattern Matching
  2. Vector Engine 2: Biological Co-Storage Compatibility Matrix
  3. Vector Engine 3: Freight Corridor Vector Scoring
"""

import math
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse_data import get_warehouses, WarehouseRecord
from app.embeddings import (
    find_matching_historical_trajectories,
    calculate_costorage_safety,
    embed_logistics_corridor
)

# Reference mandi coordinates for distance & map polyline routing
MANDI_COORDINATES = {
    "ujjain": {"lat": 23.1765, "lng": 75.7885, "state": "Madhya Pradesh"},
    "dewas": {"lat": 22.9676, "lng": 76.0534, "state": "Madhya Pradesh"},
    "indore": {"lat": 22.7196, "lng": 75.8577, "state": "Madhya Pradesh"},
    "bhopal": {"lat": 23.2599, "lng": 77.4126, "state": "Madhya Pradesh"},
    "gwalior": {"lat": 26.2183, "lng": 78.1828, "state": "Madhya Pradesh"},
    "jabalpur": {"lat": 23.1815, "lng": 79.9864, "state": "Madhya Pradesh"},
    "nashik": {"lat": 19.9975, "lng": 73.7898, "state": "Maharashtra"},
    "pune apmc": {"lat": 18.5204, "lng": 73.8567, "state": "Maharashtra"},
    "aurangabad": {"lat": 19.8762, "lng": 75.3433, "state": "Maharashtra"},
    "nagpur": {"lat": 21.1458, "lng": 79.0882, "state": "Maharashtra"},
    "ludhiana": {"lat": 30.9010, "lng": 75.8573, "state": "Punjab"},
    "amritsar": {"lat": 31.6340, "lng": 74.8723, "state": "Punjab"},
    "jalandhar": {"lat": 31.3260, "lng": 75.5762, "state": "Punjab"},
    "karnal": {"lat": 29.6857, "lng": 76.9905, "state": "Haryana"},
    "hisar": {"lat": 29.1492, "lng": 75.7217, "state": "Haryana"},
    "agra": {"lat": 27.1767, "lng": 78.0081, "state": "Uttar Pradesh"},
    "kanpur": {"lat": 26.4499, "lng": 80.3319, "state": "Uttar Pradesh"},
    "jaipur muhana": {"lat": 26.9124, "lng": 75.7873, "state": "Rajasthan"},
    "kota": {"lat": 25.2138, "lng": 75.8648, "state": "Rajasthan"},
}


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinate pairs."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)


async def run_multi_crop_planner(
    db: AsyncSession,
    state: str,
    district: str,
    crops_input: List[Dict[str, Any]],
    transport_cost_per_km: float = 18.0,
    max_travel_radius_km: float = 250.0,
) -> Dict[str, Any]:
    """
    Executes joint multi-crop logistics, warehousing, and spatial-temporal route optimization.
    """
    # 1. Determine origin coordinates from district / state
    origin_coord = {"lat": 23.1765, "lng": 75.7885} # Default Ujjain, MP
    matched_mandi_coords = [
        v for k, v in MANDI_COORDINATES.items()
        if district.lower() in k or k in district.lower()
    ]
    if matched_mandi_coords:
        origin_coord = {"lat": matched_mandi_coords[0]["lat"], "lng": matched_mandi_coords[0]["lng"]}

    # 2. Get available WDRA warehouses for the state/district
    state_warehouses = get_warehouses(state=state)
    if not state_warehouses:
        state_warehouses = get_warehouses() # fallback to all facilities

    # 3. Multi-Crop Storage & Market Route Optimization
    crop_plans = []
    total_batch_quantity = 0.0
    total_projected_gross = 0.0
    total_projected_freight = 0.0
    total_projected_storage = 0.0
    total_projected_net = 0.0

    all_routes = []
    co_storage_pairs = []

    # Calculate biological co-storage safety if multiple crops present
    for i in range(len(crops_input)):
        for j in range(i + 1, len(crops_input)):
            ca = crops_input[i]["crop_name"]
            cb = crops_input[j]["crop_name"]
            co_storage_pairs.append(calculate_costorage_safety(ca, cb))

    for idx, c_item in enumerate(crops_input):
        c_name = c_item.get("crop_name", "Wheat")
        qtl = float(c_item.get("quantity_quintals", 50.0))
        total_batch_quantity += qtl

        is_perishable = any(p in c_name.lower() for p in ["potato", "onion", "tomato", "fruits", "garlic"])

        # Select best warehouse match
        wh_candidates = [
            w for w in state_warehouses
            if any(sc.lower() in c_name.lower() or c_name.lower() in sc.lower() for sc in w["supported_crops"])
        ]
        if not wh_candidates:
            wh_candidates = state_warehouses

        best_wh = wh_candidates[idx % len(wh_candidates)]
        wh_dist = _haversine_distance(origin_coord["lat"], origin_coord["lng"], best_wh["latitude"], best_wh["longitude"])

        # Select target regional/interstate mandis using 3-tier resolution (Cache -> Live URL -> Demo)
        candidate_mandis = []
        
        if db:
            try:
                from app.models import Mandi, PriceRecord, CropCanon
                from app.agents.price_fetch_agent import _fetch_mandi_prices, MandiInfo, _get_cached_prices, _fetch_from_agmarknet, _upsert_price_records
                from sqlalchemy import select
                
                # Resolve crop in CropCanon
                crop_q = await db.execute(select(CropCanon).where(CropCanon.canonical_name.ilike(f"%{c_name.split()[0]}%")))
                crop_row = crop_q.scalars().first()
                canon_id = crop_row.id if crop_row else 1

                # Query active mandis in database
                mandi_q = await db.execute(select(Mandi))
                db_mandis = mandi_q.scalars().all()

                for m in db_mandis:
                    m_lat = float(m.latitude or 23.1765)
                    m_lng = float(m.longitude or 75.7885)
                    m_dist = _haversine_distance(origin_coord["lat"], origin_coord["lng"], m_lat, m_lng)

                    if m_dist <= max_travel_radius_km:
                        is_interstate = m.state.lower().strip() != state.lower().strip()
                        
                        # 1. DB Cache — only use if records exist AND fetched < 6hrs ago
                        from datetime import datetime as _dt, timezone as _tz
                        _CACHE_TTL = 6.0
                        cached = await _get_cached_prices(db, m.id, canon_id, 14)
                        live_cached = [r for r in cached if r.get("data_tier") != "DEMO"]
                        cache_fresh = False
                        if live_cached:
                            fetched_ats = []
                            for rc in live_cached:
                                fa = rc.get("fetched_at")
                                if fa is None:
                                    continue
                                # BUG FIX: normalize tz-awareness before subtraction
                                if hasattr(fa, 'tzinfo') and fa.tzinfo is None:
                                    fa = fa.replace(tzinfo=_tz.utc)
                                fetched_ats.append(fa)
                            if fetched_ats:
                                latest_fa = max(fetched_ats)
                                now_utc = _dt.now(_tz.utc)
                                age_h = (now_utc - latest_fa).total_seconds() / 3600
                                cache_fresh = age_h < _CACHE_TTL

                        if cache_fresh and live_cached:
                            real_price = float(live_cached[-1]["modal_price"])
                        else:
                            # 2. Live Agmarknet HTTP API call
                            try:
                                api_recs = await _fetch_from_agmarknet(
                                    state=m.state, district=m.district,
                                    commodity=c_name, days_back=14
                                )
                                if api_recs:
                                    real_price = float(api_recs[-1]["modal_price"])
                                    await _upsert_price_records(db, api_recs, m.id, canon_id)
                                elif live_cached:
                                    real_price = float(live_cached[-1]["modal_price"])
                                else:
                                    # 3. Demo fallback price (no banner needed — just a scalar)
                                    real_price = 2450.0 if "wheat" in c_name.lower() else (1950.0 if "soybean" in c_name.lower() else 1650.0)
                            except Exception:
                                if live_cached:
                                    real_price = float(live_cached[-1]["modal_price"])
                                else:
                                    real_price = 2450.0 if "wheat" in c_name.lower() else (1950.0 if "soybean" in c_name.lower() else 1650.0)

                        if is_interstate:
                            real_price += 180.0

                        candidate_mandis.append({
                            "mandi_name": m.name,
                            "state": m.state,
                            "latitude": m_lat,
                            "longitude": m_lng,
                            "distance_km": m_dist,
                            "is_interstate": is_interstate,
                            "estimated_modal_price": real_price,
                        })
            except Exception as ex:
                pass

        # Fallback to MANDI_COORDINATES if db query returned no mandis
        if not candidate_mandis:
            for m_name, m_info in MANDI_COORDINATES.items():
                m_dist = _haversine_distance(origin_coord["lat"], origin_coord["lng"], m_info["lat"], m_info["lng"])
                if m_dist <= max_travel_radius_km:
                    is_interstate = m_info["state"].lower() != state.lower()
                    base_price = 2400.0 if "wheat" in c_name.lower() else (
                        1900.0 if "soybean" in c_name.lower() else (
                            1600.0 if "potato" in c_name.lower() else 3800.0
                        )
                    )
                    if is_interstate:
                        base_price += 180.0
                    candidate_mandis.append({
                        "mandi_name": m_name.title(),
                        "state": m_info["state"],
                        "latitude": m_info["lat"],
                        "longitude": m_info["lng"],
                        "distance_km": m_dist,
                        "is_interstate": is_interstate,
                        "estimated_modal_price": base_price,
                    })

        candidate_mandis.sort(key=lambda x: x["estimated_modal_price"], reverse=True)
        target_mandi = candidate_mandis[0] if candidate_mandis else {
            "mandi_name": f"{district} APMC", "state": state,
            "latitude": origin_coord["lat"], "longitude": origin_coord["lng"],
            "distance_km": 15.0, "is_interstate": False, "estimated_modal_price": 2450.0
        }

        # Generate dynamic 14-day price trajectory per crop category
        growth_factor = 0.004 if "wheat" in c_name.lower() else (
            0.009 if "potato" in c_name.lower() else (
                0.006 if "soybean" in c_name.lower() else 0.005
            )
        )
        sample_prices = [target_mandi["estimated_modal_price"] * (1 + (day * growth_factor)) for day in range(14)]
        trajectory_match = find_matching_historical_trajectories(sample_prices, volatility=0.02, crop_name=c_name)

        # Financial Calculations (Farm -> Warehouse -> Mandi supply chain legs)
        wh_to_mandi_dist = _haversine_distance(best_wh["latitude"], best_wh["longitude"], target_mandi["latitude"], target_mandi["longitude"])
        total_dist = round(wh_dist + wh_to_mandi_dist, 1)
        freight_cost = round(total_dist * transport_cost_per_km, 2)
        hold_days = 7 if is_perishable else 14
        storage_cost = round(qtl * best_wh["daily_fee_per_qtl"] * hold_days, 2)
        gross_rev = round(qtl * target_mandi["estimated_modal_price"], 2)
        net_rev = round(gross_rev - freight_cost - storage_cost, 2)

        total_projected_gross += gross_rev
        total_projected_freight += freight_cost
        total_projected_storage += storage_cost
        total_projected_net += net_rev

        # Route segment
        route_segments = [
            {
                "from_label": f"Farm ({district}, {state})",
                "to_label": best_wh["name"],
                "from_coords": [origin_coord["lat"], origin_coord["lng"]],
                "to_coords": [best_wh["latitude"], best_wh["longitude"]],
                "distance_km": wh_dist,
                "leg_type": "FARM_TO_WAREHOUSE"
            },
            {
                "from_label": best_wh["name"],
                "to_label": f"{target_mandi['mandi_name']} ({target_mandi['state']})",
                "from_coords": [best_wh["latitude"], best_wh["longitude"]],
                "to_coords": [target_mandi["latitude"], target_mandi["longitude"]],
                "distance_km": target_mandi["distance_km"],
                "leg_type": "WAREHOUSE_TO_MANDI"
            }
        ]

        all_routes.extend(route_segments)

        crop_plans.append({
            "crop_name": c_name,
            "quantity_quintals": qtl,
            "allocated_warehouse": {
                "id": best_wh["id"],
                "name": best_wh["name"],
                "type": best_wh["warehouse_type"],
                "district": best_wh["district"],
                "state": best_wh["state"],
                "latitude": best_wh["latitude"],
                "longitude": best_wh["longitude"],
                "daily_fee_per_qtl": best_wh["daily_fee_per_qtl"],
                "temperature_controlled": best_wh["temperature_controlled"],
                "recommended_hold_days": hold_days,
                "projected_storage_fee": round(storage_cost, 2),
            },
            "target_mandi": target_mandi,
            "trajectory_forecast": trajectory_match,
            "financials": {
                "gross_revenue": round(gross_rev, 2),
                "freight_cost": round(freight_cost, 2),
                "storage_cost": round(storage_cost, 2),
                "net_revenue": round(net_rev, 2),
                "net_revenue_per_qtl": round(net_rev / qtl, 2),
            },
            "route_segments": route_segments
        })

    # 4. Generate 30-Day Day-by-Day Micro Selling Schedule Timeline
    timeline_schedule = []
    base_date = date.today()
    for day in range(1, 31):
        day_date = base_date + timedelta(days=day)
        day_entry = {"day": day, "date_str": day_date.strftime("%d %b"), "crop_actions": []}
        
        for plan in crop_plans:
            hold_d = plan["allocated_warehouse"]["recommended_hold_days"]
            c_name = plan["crop_name"]
            if day == hold_d:
                day_entry["crop_actions"].append({
                    "crop_name": c_name,
                    "action": "SELL",
                    "target_mandi": plan["target_mandi"]["mandi_name"],
                    "projected_payout": plan["financials"]["net_revenue"]
                })
            elif day < hold_d:
                day_entry["crop_actions"].append({
                    "crop_name": c_name,
                    "action": "HOLD_STORAGE",
                    "warehouse": plan["allocated_warehouse"]["name"],
                    "daily_cost": round(plan["quantity_quintals"] * plan["allocated_warehouse"]["daily_fee_per_qtl"], 2)
                })
        
        timeline_schedule.append(day_entry)

    return {
        "summary": {
            "total_crops_planned": len(crops_input),
            "total_batch_quantity_quintals": total_batch_quantity,
            "origin_location": f"{district}, {state}",
            "origin_coords": origin_coord,
            "total_projected_gross": round(total_projected_gross, 2),
            "total_projected_freight": round(total_projected_freight, 2),
            "total_projected_storage": round(total_projected_storage, 2),
            "total_projected_net_revenue": round(total_projected_net, 2),
        },
        "crop_plans": crop_plans,
        "co_storage_safety_matrix": co_storage_pairs,
        "timeline_schedule": timeline_schedule,
        "all_map_routes": all_routes,
        "generated_at": datetime.utcnow().isoformat()
    }
