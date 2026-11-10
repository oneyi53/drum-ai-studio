from fastapi.testclient import TestClient

from app.main import app


def setup_client(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    main.initialize_storage()
    return TestClient(app)


def create_project(client: TestClient) -> str:
    response = client.post(
        "/api/projects",
        files={"audio": ("practice.wav", b"fake audio bytes", "audio/wav")},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_reference_events_round_trip(tmp_path, monkeypatch) -> None:
    with setup_client(tmp_path, monkeypatch) as client:
        project_id = create_project(client)
        events = [
            {"id": 1, "onset_seconds": 0.125, "instrument": "kick"},
            {"id": 2, "onset_seconds": 0.5, "instrument": "snare"},
        ]
        saved = client.put(
            f"/api/projects/{project_id}/reference-events",
            json={"events": events},
        )
        assert saved.status_code == 200
        assert saved.json()["saved_events"] == 2
        loaded = client.get(f"/api/projects/{project_id}/reference-events")
        assert loaded.status_code == 200
        assert loaded.json() == {"project_id": project_id, "events": events}


def test_empty_list_clears_existing_events(tmp_path, monkeypatch) -> None:
    with setup_client(tmp_path, monkeypatch) as client:
        project_id = create_project(client)
        client.put(
            f"/api/projects/{project_id}/reference-events",
            json={"events": [{"id": 1, "onset_seconds": 0.25, "instrument": "kick"}]},
        )
        cleared = client.put(
            f"/api/projects/{project_id}/reference-events", json={"events": []}
        )
        assert cleared.status_code == 200
        assert cleared.json()["saved_events"] == 0
        assert client.get(
            f"/api/projects/{project_id}/reference-events"
        ).json()["events"] == []


def test_invalid_instrument_and_negative_onset_are_rejected(
    tmp_path, monkeypatch
) -> None:
    with setup_client(tmp_path, monkeypatch) as client:
        project_id = create_project(client)
        invalid_instrument = client.put(
            f"/api/projects/{project_id}/reference-events",
            json={"events": [{"id": 1, "onset_seconds": 0.1, "instrument": "guitar"}]},
        )
        negative_onset = client.put(
            f"/api/projects/{project_id}/reference-events",
            json={"events": [{"id": 1, "onset_seconds": -0.1, "instrument": "kick"}]},
        )
        assert invalid_instrument.status_code == 422
        assert negative_onset.status_code == 422


def test_missing_project_returns_404(tmp_path, monkeypatch) -> None:
    with setup_client(tmp_path, monkeypatch) as client:
        missing = "does-not-exist"
        assert client.get(f"/api/projects/{missing}/reference-events").status_code == 404
        assert client.put(
            f"/api/projects/{missing}/reference-events", json={"events": []}
        ).status_code == 404


def test_duplicate_event_ids_are_rejected(tmp_path, monkeypatch) -> None:
    with setup_client(tmp_path, monkeypatch) as client:
        project_id = create_project(client)
        response = client.put(
            f"/api/projects/{project_id}/reference-events",
            json={
                "events": [
                    {"id": 1, "onset_seconds": 0.1, "instrument": "kick"},
                    {"id": 1, "onset_seconds": 0.2, "instrument": "snare"},
                ]
            },
        )
        assert response.status_code == 422
