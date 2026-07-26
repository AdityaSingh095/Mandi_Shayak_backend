"""
backend/app/main.py
─────────────────────────────────────────────────────────
FastAPI application factory.
Mounts all routers, configures CORS, and runs DB init on startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.routers import health, intake, analyze, history, mandis, crops, profiles, cron

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize DB tables and pre-warm embedding model."""
    settings = get_settings()
    logger.info(f"Starting Mandi Sahayak API [env={settings.environment}]")

    if settings.is_sqlite or settings.environment == "local":
        await init_db()
        logger.info("Database tables initialized.")

    try:
        from app.embeddings import get_embedder
        get_embedder()
        logger.info("Embedding model pre-warmed.")
    except Exception as e:
        logger.warning(f"Embedding model unavailable (keyword fallback active): {e}")

    yield
    logger.info("Mandi Sahayak API shutting down.")


app = FastAPI(
    title="Mandi Sahayak API",
    description=(
        "Non-generative mandi price intelligence and sell-timing advisory. "
        "Powers the Mandi Sahayak farmer decision support system."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. Please try again.",
            "detail": str(exc) if settings.environment == "local" else None,
        },
    )


from app.routers import health, intake, analyze, history, mandis, crops, profiles, cron, multimodal, simulator, report, warehouses, planner, vault

# ── Routers (Mounted with /api and root fallbacks to guarantee zero 404s on Vercel) ──
for pfx in ["/api", ""]:
    app.include_router(health.router,        prefix=pfx)
    app.include_router(intake.router,        prefix=pfx)
    app.include_router(analyze.router,       prefix=pfx)
    app.include_router(history.router,       prefix=pfx)
    app.include_router(mandis.mandis_router, prefix=pfx)
    app.include_router(crops.router,         prefix=pfx)
    app.include_router(profiles.router,      prefix=pfx)
    app.include_router(cron.router,          prefix=pfx)
    app.include_router(multimodal.router,    prefix=pfx)
    app.include_router(simulator.router,     prefix=pfx)
    app.include_router(report.router,        prefix=pfx)
    app.include_router(warehouses.router,    prefix=pfx)
    app.include_router(planner.router,       prefix=pfx)
    app.include_router(vault.router,         prefix=pfx)


@app.get("/")
async def root():
    return {"message": "Mandi Sahayak API", "docs": "/api/docs"}
