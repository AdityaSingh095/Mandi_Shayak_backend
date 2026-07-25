"""
app/agents/normalization_agent.py
─────────────────────────────────────────────────────────
Agent 3: Resolves raw crop name → canonical CropCanon row.
Uses fastembed + pgvector (Postgres) or cosine sim on stored vectors (SQLite).
Falls back to keyword dictionary if fastembed unavailable.
"""

import json
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import PipelineContext, CropInfo
from app.models import CropCanon, FarmerCrop
from app.embeddings import embed_text, build_crop_embed_text, cosine_similarity
from app.config import get_settings, cfg_float

logger = logging.getLogger(__name__)

# ── Keyword fallback dictionary ───────────────────────────────────────────────
KEYWORD_MAP = {
    "wheat": "Wheat", "gehun": "Wheat", "gehu": "Wheat", "kanak": "Wheat",
    "gehun sharbati": "Wheat", "sharbati": "Wheat",
    "mustard": "Mustard", "sarson": "Mustard", "rai": "Mustard", "lahi": "Mustard",
    "rape seed": "Mustard", "rapeseed": "Mustard",
    "gram": "Gram", "chana": "Gram", "channa": "Gram", "chickpea": "Gram",
    "bengal gram": "Gram", "kabuli chana": "Gram",
    "soybean": "Soybean", "soya bean": "Soybean", "soyabean": "Soybean", "soya": "Soybean",
    "onion": "Onion", "pyaaz": "Onion", "kanda": "Onion", "pyaz": "Onion",
    "tomato": "Tomato", "tamatar": "Tomato", "tamato": "Tomato",
    "potato": "Potato", "aalu": "Potato", "aalo": "Potato", "batata": "Potato",
    "maize": "Maize", "makka": "Maize", "makki": "Maize", "corn": "Maize",
    "cotton": "Cotton", "kapas": "Cotton", "rui": "Cotton",
    "paddy": "Paddy", "dhan": "Paddy", "rice": "Paddy",
    "bajra": "Bajra", "pearl millet": "Bajra",
    "jowar": "Jowar", "sorghum": "Jowar",
    "groundnut": "Groundnut", "moongphali": "Groundnut", "peanut": "Groundnut",
    "sugarcane": "Sugarcane", "ganna": "Sugarcane",
}


async def run_normalization_agent(
    db: AsyncSession, ctx: PipelineContext, raw_crop_name: str
) -> PipelineContext:
    """
    Resolves `raw_crop_name` to a canonical CropCanon entry.
    Writes the resolved crop info into ctx.crop.
    """
    settings = get_settings()
    auto_threshold = cfg_float("normalization.auto_resolve_threshold", 0.85)
    confirm_threshold = cfg_float("normalization.confirm_threshold", 0.75)
    reject_threshold = cfg_float("normalization.reject_threshold", 0.60)

    cleaned = raw_crop_name.strip().lower()
    candidates = []

    # ── Try vector search (Postgres + fastembed) ───────────────────────────
    query_vector = embed_text(raw_crop_name)

    if query_vector and not settings.is_sqlite:
        # Postgres: use pgvector operator directly
        candidates = await _vector_search_postgres(db, query_vector, reject_threshold)
    elif query_vector and settings.is_sqlite:
        # SQLite: load all embeddings, compute cosine in Python
        candidates = await _vector_search_sqlite(db, query_vector, reject_threshold)

    # ── Fallback: keyword dictionary ──────────────────────────────────────
    if not candidates:
        candidates = await _keyword_search(db, cleaned)

    if not candidates:
        # Dynamic fallback: Auto-register the new crop in CropCanon so analysis can proceed!
        try:
            formatted_name = raw_crop_name.strip().title()
            new_crop = CropCanon(
                canonical_name=formatted_name,
                variety="Generic",
                is_perishable=False,
                shelf_life_days=30,
            )
            db.add(new_crop)
            await db.commit()
            await db.refresh(new_crop)
            
            candidates = [{
                "id": new_crop.id,
                "canonical_name": new_crop.canonical_name,
                "variety": new_crop.variety,
                "is_perishable": new_crop.is_perishable,
                "shelf_life_days": new_crop.shelf_life_days,
                "similarity": 1.0,
                "keyword_match": True,
            }]
            logger.info(f"Registered new crop dynamically: {formatted_name}")
        except Exception as e:
            await db.rollback()
            logger.error(f"Dynamic crop registration failed: {e}")
            ctx.append_audit(
                agent_name="NORMALIZATION",
                message=f'Crop "{raw_crop_name}" could not be matched to any known crop.',
                technical_detail=str(e),
            )
            return ctx

    best = candidates[0]
    score = best.get("similarity", 0.0)

    # ── Apply threshold policy ─────────────────────────────────────────────
    if score >= confirm_threshold or best.get("keyword_match", False):
        confidence = "HIGH" if score >= auto_threshold else "MEDIUM"
        crop_row = await db.get(CropCanon, best["id"])
        if crop_row:
            ctx.crop = CropInfo(
                id=crop_row.id,
                canonical_name=crop_row.canonical_name,
                variety=crop_row.variety,
                is_perishable=crop_row.is_perishable,
                shelf_life_days=crop_row.shelf_life_days,
                aliases=crop_row.get_aliases(),
            )
            ctx.normalization_confidence = score
            ctx.normalization_candidates = candidates

            # Update the FarmerCrop row with the resolved canonical_crop_id
            try:
                fc = await db.get(FarmerCrop, ctx.farmer_crop_id)
                if fc:
                    fc.canonical_crop_id = crop_row.id
                    await db.commit()
            except Exception as e:
                await db.rollback()
                logger.warning(f"Could not update farmer_crop canonical_crop_id: {e}")

            variety_str = f" ({crop_row.variety})" if crop_row.variety else ""
            ctx.append_audit(
                agent_name="NORMALIZATION",
                message=(
                    f'Input "{raw_crop_name}" matched to '
                    f'{crop_row.canonical_name}{variety_str} with {confidence.lower()} confidence.'
                ),
                technical_detail=(
                    f"Similarity score = {score:.2f}. Threshold = {confirm_threshold}. "
                    f"Top match: crop_id={crop_row.id}. "
                    f"Candidates: {[c.get('canonical_name') for c in candidates[:3]]}."
                ),
            )
    else:
        ctx.normalization_candidates = candidates
        ctx.append_audit(
            agent_name="NORMALIZATION",
            message=(
                f'Input "{raw_crop_name}" matched with LOW confidence ({score:.2f}). '
                f"Showing top candidates for confirmation."
            ),
            technical_detail=f"Reject threshold: {reject_threshold}. Best score: {score:.2f}.",
        )

    return ctx


async def _vector_search_postgres(db: AsyncSession, query_vector: list[float], threshold: float) -> list[dict]:
    """Cosine similarity via pgvector operator — Postgres only."""
    try:
        result = await db.execute(
            text("""
                SELECT id, canonical_name, variety, is_perishable, shelf_life_days,
                       1 - (embedding_json::vector <=> CAST(:vec AS vector)) AS similarity
                FROM crop_canon
                WHERE 1 - (embedding_json::vector <=> CAST(:vec AS vector)) > :threshold
                ORDER BY embedding_json::vector <=> CAST(:vec AS vector)
                LIMIT 3
            """),
            {"vec": str(query_vector), "threshold": threshold},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Postgres vector search failed, falling back to keyword: {e}")
        return []


async def _vector_search_sqlite(db: AsyncSession, query_vector: list[float], threshold: float) -> list[dict]:
    """Cosine similarity computed in Python — SQLite fallback."""
    result = await db.execute(select(CropCanon))
    all_crops = result.scalars().all()
    scored = []
    for crop in all_crops:
        stored_vec = crop.get_embedding()
        if stored_vec:
            sim = cosine_similarity(query_vector, stored_vec)
            if sim >= threshold:
                scored.append({
                    "id": crop.id,
                    "canonical_name": crop.canonical_name,
                    "variety": crop.variety,
                    "is_perishable": crop.is_perishable,
                    "shelf_life_days": crop.shelf_life_days,
                    "similarity": sim,
                })
    return sorted(scored, key=lambda x: x["similarity"], reverse=True)[:3]


async def _keyword_search(db: AsyncSession, cleaned_input: str) -> list[dict]:
    """Keyword dictionary search — no embeddings needed."""
    canonical_name = KEYWORD_MAP.get(cleaned_input)
    if not canonical_name:
        # Partial match
        for kw, name in KEYWORD_MAP.items():
            if kw in cleaned_input or cleaned_input in kw:
                canonical_name = name
                break
    if not canonical_name:
        return []

    result = await db.execute(
        select(CropCanon).where(CropCanon.canonical_name == canonical_name).limit(1)
    )
    crop = result.scalar_one_or_none()
    if not crop:
        return []

    return [{
        "id": crop.id,
        "canonical_name": crop.canonical_name,
        "variety": crop.variety,
        "is_perishable": crop.is_perishable,
        "shelf_life_days": crop.shelf_life_days,
        "similarity": 1.0,  # Exact/direct keyword match is HIGH confidence (auto-resolves)
        "keyword_match": True,
    }]
