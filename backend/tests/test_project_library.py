from fastapi.testclient import TestClient

from app.main import app


def isolated_client(tmp_path, monkeypatch) -> TestClient:
    from app import main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    main.initialize_storage()
    return TestClient(app)


def test_list_projects_and_download_original_audio(tmp_path, monkeypatch) -> None:
    with isolated_client(tmp_path, monkeypatch) as client:
        audio_bytes = b"RIFF-test-audio-bytes"
        created = client.post(
            "/api/projects",
            files={"audio": ("session.wav", audio_bytes, "audio/wav")},
        )
        assert created.status_code == 200
        project_id = created.json()["id"]

        listing = client.get("/api/projects")
        assert listing.status_code == 200
        assert len(listing.json()["projects"]) == 1
        project = listing.json()["projects"][0]
        assert project["id"] == project_id
        assert project["filename"] == "session.wav"
        assert project["size_bytes"] == len(audio_bytes)

        audio = client.get(f"/api/projects/{project_id}/audio")
        assert audio.status_code == 200
        assert audio.content == audio_bytes
        assert "session.wav" in audio.headers["content-disposition"]


def test_project_audio_returns_404_for_unknown_project(tmp_path, monkeypatch) -> None:
    with isolated_client(tmp_path, monkeypatch) as client:
        response = client.get("/api/projects/missing/audio")
        assert response.status_code == 404


def test_project_list_is_empty_before_upload(tmp_path, monkeypatch) -> None:
    with isolated_client(tmp_path, monkeypatch) as client:
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == {"projects": []}
