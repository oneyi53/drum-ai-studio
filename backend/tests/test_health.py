from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_engine_not_configured() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transcription_engine"] == "not_configured"


def test_analysis_is_not_falsely_enabled() -> None:
    response = client.post("/api/projects/not-a-real-project/analyze")
    assert response.status_code == 501
    assert "not integrated" in response.json()["detail"]
