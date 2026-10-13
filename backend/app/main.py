from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title="BillSplit API", version="0.1.0")

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    """Unversioned health check - confirms the app boots and env config loaded."""
    return {
        "status": "ok",
        "env": settings.ENV,
        "db_loaded": bool(settings.DATABASE_URL),
    }
