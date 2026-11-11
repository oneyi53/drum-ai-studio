from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_engine_installation_state() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transcription_engine"] in {"available", "not_installed"}


def test_analysis_requires_an_existing_project() -> None:
    with TestClient(app) as client:
        response = client.post("/api/projects/not-a-real-project/analyze")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."
