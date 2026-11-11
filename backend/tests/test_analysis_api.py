from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(main, "ANALYSIS_DIR", tmp_path / "data" / "analysis")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "data" / "test.sqlite3")
    with TestClient(main.app) as test_client:
        yield test_client


def test_upload_creates_project_and_rejects_unsupported_type(client):
    response = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "uploaded"
    assert (main.UPLOAD_DIR / f"{response.json()['id']}.wav").is_file()

    unsupported = client.post(
        "/api/projects",
        files={"audio": ("demo.txt", b"nope", "text/plain")},
    )
    assert unsupported.status_code == 415


def test_analysis_job_persists_canonical_performance(client, monkeypatch):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=3,
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, source="model")
        ],
    )

    def fake_run(job_id: str) -> None:
        with main.connect_db() as connection:
            job = connection.execute(
                "SELECT project_id FROM analysis_jobs WHERE id=?", (job_id,)
            ).fetchone()
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status='completed', performance_json=?, midi_filename='performance.mid'
                WHERE id=?
                """,
                (performance.model_dump_json(), job_id),
            )
            connection.execute(
                "UPDATE projects SET status='analyzed' WHERE id=?", (job["project_id"],)
            )

    monkeypatch.setattr(main, "run_analysis_job", fake_run)
    created = client.post(f"/api/projects/{uploaded['id']}/analyze")
    assert created.status_code == 202
    job_id = created.json()["job_id"]

    job = client.get(f"/api/analysis-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"

    result = client.get(f"/api/projects/{uploaded['id']}/performance")
    assert result.status_code == 200
    assert result.json()["performance"]["events"][0]["instrument"] == "kick"


def test_duplicate_active_job_is_rejected(client, monkeypatch):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    # Prevent BackgroundTasks from consuming the queued job in this request.
    monkeypatch.setattr(main, "run_analysis_job", lambda job_id: None)
    first = client.post(f"/api/projects/{uploaded['id']}/analyze")
    assert first.status_code == 202
    second = client.post(f"/api/projects/{uploaded['id']}/analyze")
    assert second.status_code == 409


def test_missing_project_and_job_return_404(client):
    assert client.post("/api/projects/missing/analyze").status_code == 404
    assert client.get("/api/analysis-jobs/missing").status_code == 404
    assert client.get("/api/projects/missing/performance").status_code == 404


def test_engine_failure_is_saved_as_failed_job(client, monkeypatch):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()

    class BrokenEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            raise RuntimeError("test engine failure")

    monkeypatch.setattr(main, "DrumScriptEngine", BrokenEngine)
    created = client.post(f"/api/projects/{uploaded['id']}/analyze")
    job = client.get(f"/api/analysis-jobs/{created.json()['job_id']}")
    assert job.json()["status"] == "failed"
    assert "test engine failure" in job.json()["error_message"]
