from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jera_fx_api.api.v1.client import router as client_router
from jera_fx_api.api.v1.meta import router as meta_router

app = FastAPI(title="JERA FX Foundation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(meta_router)
app.include_router(client_router)

