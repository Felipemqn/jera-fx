from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jera_fx_api.api.v1.client import router as client_router
from jera_fx_api.api.v1.investment import router as investment_router
from jera_fx_api.api.v1.meta import router as meta_router


DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"


def _cors_origins() -> list[str]:
    """Read CORS_ALLOWED_ORIGINS as CSV. Falls back to local dev origins."""
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS)
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="JERA FX Foundation API", version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(meta_router)
app.include_router(client_router)
app.include_router(investment_router)

