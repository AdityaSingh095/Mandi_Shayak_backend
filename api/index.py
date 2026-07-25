"""
backend/api/index.py
─────────────────────────────────────────────────────────
Vercel serverless entrypoint.
Mangum wraps the FastAPI ASGI app into an AWS Lambda handler.
"""

from mangum import Mangum
from app.main import app

handler = Mangum(app, lifespan="off")
