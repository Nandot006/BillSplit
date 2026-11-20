import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings

# design.md SS1: structured logs to stdout. Render (and any other host)
# captures stdout, so this is all the log plumbing v1 needs.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="BillSplit API", version="0.1.0")

# The web app runs on a different origin (Vercel) from this API (Render), so
# browsers need explicit CORS permission to call it. Origins come from env
# (CORS_ORIGINS / CORS_ORIGIN_REGEX) rather than being hardcoded, so a new
# deploy URL is a dashboard change, not a code change. Auth is a bearer
# token header, not cookies, so allow_credentials stays off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    """Unversioned health check - confirms the app boots and env config
    loaded. Also what Render's health check pings."""
    return {
        "status": "ok",
        "env": settings.ENV,
        "db_loaded": bool(settings.DATABASE_URL),
    }
