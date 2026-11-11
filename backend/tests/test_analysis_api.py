from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance
from app.midi_adapter import midi_to_performance


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

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    created = client.post(f"/api/projects/{uploaded['id']}/analyze")
    assert created.status_code == 202
    job_id = created.json()["job_id"]

    job = client.get(f"/api/analysis-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"

    result = client.get(f"/api/projects/{uploaded['id']}/performance")
    assert result.status_code == 200
    assert result.json()["performance"]["events"][0]["instrument"] == "kick"
    assert result.json()["midi_filename"] == "performance.mid"
    download = client.get(f"/api/projects/{uploaded['id']}/midi")
    assert download.status_code == 200
    assert download.content == b"fake-midi"


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


def test_midi_download_requires_completed_artifact(client):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    assert client.get(f"/api/projects/{uploaded['id']}/midi").status_code == 404


def test_manual_event_create_update_and_delete(client, monkeypatch, tmp_path):
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

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    client.post(f"/api/projects/{uploaded['id']}/analyze")

    created = client.post(
        f"/api/projects/{uploaded['id']}/events",
        json={"time_seconds": 1.25, "instrument": "snare", "velocity": 110},
    )
    assert created.status_code == 201
    event = created.json()["event"]
    assert event["source"] == "manual"
    assert event["manually_corrected"] is True

    updated = client.patch(
        f"/api/projects/{uploaded['id']}/events/{event['id']}",
        json={"time_seconds": 1.5, "instrument": "closed_hihat", "velocity": 75},
    )
    assert updated.status_code == 200
    changed = updated.json()["event"]
    assert changed["time_seconds"] == 1.5
    assert changed["instrument"] == "closed_hihat"
    assert changed["velocity"] == 75
    assert changed["manually_corrected"] is True

    result = client.get(f"/api/projects/{uploaded['id']}/performance").json()
    assert len(result["performance"]["events"]) == 2

    deleted = client.delete(
        f"/api/projects/{uploaded['id']}/events/{event['id']}"
    )
    assert deleted.status_code == 200
    remaining = client.get(f"/api/projects/{uploaded['id']}/performance").json()
    assert len(remaining["performance"]["events"]) == 1
    midi_path = tmp_path / "edited.mid"
    midi_path.write_bytes(client.get(f"/api/projects/{uploaded['id']}/midi").content)
    exported = midi_to_performance(midi_path)
    assert len(exported.events) == 1
    assert exported.events[0].instrument == DrumInstrument.KICK


def test_event_edit_rejects_out_of_range_time_and_unknown_event(client, monkeypatch):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=1,
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, source="model")
        ],
    )

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    client.post(f"/api/projects/{uploaded['id']}/analyze")
    current = client.get(f"/api/projects/{uploaded['id']}/performance").json()
    event_id = current["performance"]["events"][0]["id"]

    invalid = client.patch(
        f"/api/projects/{uploaded['id']}/events/{event_id}",
        json={"time_seconds": 1.5},
    )
    assert invalid.status_code == 422
    missing = client.delete(
        f"/api/projects/{uploaded['id']}/events/not-an-event"
    )
    assert missing.status_code == 404


def test_quantization_preview_and_apply_keep_midi_synchronized(client, monkeypatch, tmp_path):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=3,
        events=[
            DrumEvent(time_seconds=0.61, instrument=DrumInstrument.KICK),
            DrumEvent(time_seconds=1.12, instrument=DrumInstrument.SNARE),
        ],
    )

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    client.post(f"/api/projects/{uploaded['id']}/analyze")

    preview = client.post(
        f"/api/projects/{uploaded['id']}/quantize",
        json={"subdivision": "1/4", "strength": 100, "apply": False},
    )
    assert preview.status_code == 200
    assert preview.json()["applied"] is False
    assert preview.json()["performance"]["events"][0]["time_seconds"] == pytest.approx(0.5)
    unchanged = client.get(f"/api/projects/{uploaded['id']}/performance").json()
    assert unchanged["performance"]["events"][0]["time_seconds"] == pytest.approx(0.61)

    applied = client.post(
        f"/api/projects/{uploaded['id']}/quantize",
        json={"subdivision": "1/4", "strength": 100},
    )
    assert applied.status_code == 200
    saved = client.get(f"/api/projects/{uploaded['id']}/performance").json()
    assert saved["performance"]["events"][0]["time_seconds"] == pytest.approx(0.5)

    midi_path = tmp_path / "quantized.mid"
    midi_path.write_bytes(client.get(f"/api/projects/{uploaded['id']}/midi").content)
    exported = midi_to_performance(midi_path)
    assert exported.events[0].time_seconds == pytest.approx(0.5)


def test_quantization_rejects_unknown_subdivision(client, monkeypatch):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(duration_seconds=2, events=[])

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    client.post(f"/api/projects/{uploaded['id']}/analyze")
    response = client.post(
        f"/api/projects/{uploaded['id']}/quantize",
        json={"subdivision": "1/64"},
    )
    assert response.status_code == 422


def test_persistent_undo_redo_restores_performance_and_midi(client, monkeypatch, tmp_path):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=3,
        events=[DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK)],
    )

    class FakeEngine:
        def analyze(self, audio_path: Path, output_dir: Path):
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / "performance.mid"
            midi_path.write_bytes(b"fake-midi")
            return performance, midi_path

    monkeypatch.setattr(main, "DrumScriptEngine", FakeEngine)
    project_id = uploaded["id"]
    client.post(f"/api/projects/{project_id}/analyze")

    baseline = client.get(f"/api/projects/{project_id}/history").json()
    assert baseline["can_undo"] is False
    created = client.post(
        f"/api/projects/{project_id}/events",
        json={"time_seconds": 1.25, "instrument": "snare", "velocity": 110},
    )
    assert created.status_code == 201
    assert client.get(f"/api/projects/{project_id}/history").json()["can_undo"] is True

    undone = client.post(f"/api/projects/{project_id}/undo")
    assert undone.status_code == 200
    assert len(undone.json()["performance"]["events"]) == 1
    assert undone.json()["can_redo"] is True

    redone = client.post(f"/api/projects/{project_id}/redo")
    assert redone.status_code == 200
    assert len(redone.json()["performance"]["events"]) == 2
    assert redone.json()["can_redo"] is False

    midi_path = tmp_path / "history.mid"
    midi_path.write_bytes(client.get(f"/api/projects/{project_id}/midi").content)
    exported = midi_to_performance(midi_path)
    assert len(exported.events) == 2

    client.post(f"/api/projects/{project_id}/undo")
    client.post(
        f"/api/projects/{project_id}/events",
        json={"time_seconds": 2.0, "instrument": "crash", "velocity": 90},
    )
    assert client.get(f"/api/projects/{project_id}/history").json()["can_redo"] is False
    assert client.post(f"/api/projects/{project_id}/redo").status_code == 409



def test_project_audio_stream_returns_uploaded_audio_and_unknown_project_404(client):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("groove.wav", b"RIFF-test-audio", "audio/wav")},
    ).json()

    response = client.get(f"/api/projects/{uploaded['id']}/audio")
    assert response.status_code == 200
    assert response.content == b"RIFF-test-audio"
    assert response.headers["content-type"].startswith("audio/wav")
    assert "inline" in response.headers.get("content-disposition", "")

    missing = client.get("/api/projects/not-a-project/audio")
    assert missing.status_code == 404
