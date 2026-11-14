"""Tests for the re-editable .drumai.json project file and the annotation
CSV export: export shape, lossless import round-trip, audio-mismatch
rejection, and harness compatibility of the exported reference CSV."""
from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from evaluate_midi import load_reference

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


def _seed_project(client, monkeypatch, events=None):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=30,
        events=events
        if events is not None
        else [
            DrumEvent(
                time_seconds=0.5,
                instrument=DrumInstrument.KICK,
                velocity=100,
                source="model",
            ),
            DrumEvent(
                time_seconds=1.0,
                instrument=DrumInstrument.CLOSED_HIHAT,
                velocity=80,
                source="model",
            ),
            DrumEvent(
                time_seconds=1.5,
                instrument=DrumInstrument.SNARE,
                velocity=110,
                source="manual",
                manually_corrected=True,
            ),
        ],
        tempo_map=[],
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
    return uploaded["id"], performance


def _export(client, project_id, annotation=None):
    body = {"annotation": annotation} if annotation else None
    response = client.post(
        f"/api/projects/{project_id}/project-file", json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_export_shape_matches_performance(client, monkeypatch):
    project_id, performance = _seed_project(client, monkeypatch)
    project_file = _export(client, project_id)

    assert project_file["format"] == "drumai-project"
    assert project_file["version"] == "1.0"
    assert project_file["audio"] == {
        "project_id": project_id,
        "original_filename": "demo.wav",
    }
    assert project_file["duration_seconds"] == 30
    assert project_file["history_revision"] == 0
    assert project_file["annotation"] == {
        "status": "not_started",
        "done_bars": [],
        "note": "",
    }
    assert len(project_file["events"]) == len(performance.events)
    assert project_file["events"][2]["manually_corrected"] is True
    assert project_file["events"][2]["source"] == "manual"


def test_export_stamps_annotation_state(client, monkeypatch):
    project_id, _ = _seed_project(client, monkeypatch)
    project_file = _export(
        client,
        project_id,
        annotation={"status": "in_progress", "done_bars": [1, 2], "note": "bars 1-2 checked"},
    )
    assert project_file["annotation"]["status"] == "in_progress"
    assert project_file["annotation"]["done_bars"] == [1, 2]
    assert project_file["annotation"]["note"] == "bars 1-2 checked"


def test_import_round_trip_is_lossless_and_undoable(client, monkeypatch):
    project_id, performance = _seed_project(client, monkeypatch)
    project_file = _export(client, project_id)

    # Diverge the live performance: delete one event, move another.
    live = client.get(f"/api/projects/{project_id}/performance").json()["performance"]
    doomed = live["events"][0]["id"]
    assert client.delete(f"/api/projects/{project_id}/events/{doomed}").status_code == 200
    moved = live["events"][1]["id"]
    assert (
        client.patch(
            f"/api/projects/{project_id}/events/{moved}",
            json={"time_seconds": 2.0},
        ).status_code
        == 200
    )
    diverged = client.get(f"/api/projects/{project_id}/performance").json()["performance"]
    assert len(diverged["events"]) == len(performance.events) - 1

    imported = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "demo.drumai.json",
                BytesIO(json.dumps(project_file).encode()),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_event_count"] == len(performance.events)
    assert imported.json()["history_revision"] == 3

    restored = client.get(f"/api/projects/{project_id}/performance").json()["performance"]
    assert restored["events"] == [event.model_dump(mode="json") for event in performance.events]

    # Undo reaches the pre-import (diverged) state.
    assert client.post(f"/api/projects/{project_id}/undo").status_code == 200
    undone = client.get(f"/api/projects/{project_id}/performance").json()["performance"]
    assert len(undone["events"]) == len(performance.events) - 1


def test_import_regenerates_missing_midi_file(client, monkeypatch, tmp_path):
    project_id, performance = _seed_project(client, monkeypatch)
    project_file = _export(client, project_id)
    job_id = client.get(f"/api/projects/{project_id}/performance").json()["job_id"]
    midi_path = tmp_path / "data" / "analysis" / job_id / "performance.mid"
    assert midi_path.is_file()
    midi_path.unlink()
    midi_path.parent.rmdir()  # the whole analysis dir is gone, too

    imported = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "demo.drumai.json",
                BytesIO(json.dumps(project_file).encode()),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_event_count"] == len(performance.events)
    assert midi_path.is_file()
    restored = client.get(f"/api/projects/{project_id}/performance").json()["performance"]
    assert restored["events"] == [event.model_dump(mode="json") for event in performance.events]


def test_import_with_null_midi_filename_regenerates_it(client, monkeypatch, tmp_path):
    import sqlite3

    project_id, performance = _seed_project(client, monkeypatch)
    project_file = _export(client, project_id)
    db_path = tmp_path / "data" / "test.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE analysis_jobs SET midi_filename=NULL WHERE project_id=?",
            (project_id,),
        )
    job_id = client.get(f"/api/projects/{project_id}/performance").json()["job_id"]
    midi_path = tmp_path / "data" / "analysis" / job_id / "performance.mid"
    midi_path.unlink()

    imported = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "demo.drumai.json",
                BytesIO(json.dumps(project_file).encode()),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_event_count"] == len(performance.events)
    assert midi_path.is_file()


def test_import_rejects_mismatched_audio_and_bad_files(client, monkeypatch):
    project_id, _ = _seed_project(client, monkeypatch)
    project_file = _export(client, project_id)

    wrong_project = dict(project_file)
    wrong_project["audio"] = {"project_id": "someone-else", "original_filename": "demo.wav"}
    response = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "wrong.drumai.json",
                BytesIO(json.dumps(wrong_project).encode()),
                "application/json",
            )
        },
    )
    assert response.status_code == 422
    assert "someone-else" in response.json()["detail"]

    wrong_audio = dict(project_file)
    wrong_audio["audio"] = {"project_id": project_id, "original_filename": "other.wav"}
    response = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "wrong.drumai.json",
                BytesIO(json.dumps(wrong_audio).encode()),
                "application/json",
            )
        },
    )
    assert response.status_code == 422
    assert "other.wav" in response.json()["detail"]

    response = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={"project_file": ("bad.json", BytesIO(b"{not json"), "application/json")},
    )
    assert response.status_code == 422

    tampered = dict(project_file)
    tampered["surprise_field"] = True
    response = client.post(
        f"/api/projects/{project_id}/project-file/import",
        files={
            "project_file": (
                "bad.drumai.json",
                BytesIO(json.dumps(tampered).encode()),
                "application/json",
            )
        },
    )
    assert response.status_code == 422


def test_annotation_csv_matches_evaluator_format(client, monkeypatch, tmp_path):
    events = [
        DrumEvent(time_seconds=1.005, instrument=DrumInstrument.CLOSED_HIHAT),
        DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK),
        DrumEvent(time_seconds=2.0, instrument=DrumInstrument.OPEN_HIHAT),
        DrumEvent(time_seconds=1.5, instrument=DrumInstrument.PEDAL_HIHAT),
    ]
    project_id, _ = _seed_project(client, monkeypatch, events=events)
    response = client.get(f"/api/projects/{project_id}/annotation.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text == (
        "onset_seconds,instrument\n"
        "0.500,kick\n"
        "1.005,closed_hat\n"
        "1.500,pedal_hihat\n"
        "2.000,open_hat\n"
    )

    # The exported file loads straight into the evaluation harness.
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text(response.text, encoding="utf-8")
    reference = load_reference(csv_path)
    assert [event.instrument for event in reference] == [
        "kick",
        "closed_hat",
        "pedal_hihat",
        "open_hat",
    ]
