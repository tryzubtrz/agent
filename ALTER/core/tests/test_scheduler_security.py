from fastapi.testclient import TestClient

from api.index import app


def test_scheduler_requires_github_oidc_bearer():
    response = TestClient(app).post("/api/scheduler/tick")
    assert response.status_code == 401
    assert "oidc" in response.json()["detail"].lower()


def test_scheduler_rejects_malformed_bearer_without_network():
    response = TestClient(app).post(
        "/api/scheduler/tick",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401
