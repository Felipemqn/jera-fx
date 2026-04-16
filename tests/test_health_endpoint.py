"""Tests for the /v1/meta/health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from jera_fx_api.db.session import get_db_session
from jera_fx_api.main import app


def test_health_endpoint_returns_ok_when_db_up(session) -> None:
    def override_get_db_session():
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        client = TestClient(app)
        response = client.get("/v1/meta/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert "version" in body
        assert "timestamp" in body
    finally:
        app.dependency_overrides.clear()
