"""Tests for the tempo x2 / 1/2 toggle: scaling, anchor clamping, undo,
MIDI / MusicXML consistency, and the tempo status endpoint."""
from __future__ import annotations

from pathlib import Path

import mido
import pytest
from fastapi.testclient import TestClient

from app import main
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance, TempoChange


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(main, "ANALYSIS_DIR", tmp_path / "data" / "analysis")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "data" / "test.sqlite3")
    with TestClient(main.app) as test_client:
        yield test_client


def _seed_project(client, monkeypatch, tempo_map):
    uploaded = client.post(
        "/api/projects",
        files={"audio": ("demo.wav", b"audio-bytes", "audio/wav")},
    ).json()
    performance = DrumPerformance(
        duration_seconds=30,
        events=[
            DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK, velocity=100),
            DrumEvent(time_seconds=1.0, instrument=DrumInstrument.CLOSED_HIHAT, velocity=80),
            DrumEvent(time_seconds=1.5, instrument=DrumInstrument.SNARE, velocity=110),
        ],
        tempo_map=tempo_map,
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
    return uploaded["id"], created.json()["job_id"], performance


def _scale(client, project_id, factor):
    response = client.post(
        f"/api/projects/{project_id}/tempo", json={"factor": factor}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _midi_tempos(project_id, job_id):
    midi = mido.MidiFile(main.ANALYSIS_DIR / job_id / "performance.mid")
    return [
        round(60_000_000 / message.tempo, 1)
        for track in midi.tracks
        for message in track
        if message.type == "set_tempo"
    ]


def test_tempo_doubles_and_midi_follows(client, monkeypatch):
    project_id, job_id, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    result = _scale(client, project_id, 2)
    assert result["tempo_map"][0]["bpm"] == 280.0
    assert result["ratio"] == 2.0
    assert result["at_max"] is True
    assert result["at_min"] is False
    # Events, duration and meter are untouched; only the BPM moved.
    assert len(result["performance"]["events"]) == 3
    assert result["performance"]["duration_seconds"] == 30
    assert result["performance"]["tempo_map"][0]["numerator"] == 4
    # The regenerated MIDI carries the new tempo.
    assert _midi_tempos(project_id, job_id) == [280.0]


def test_tempo_halves(client, monkeypatch):
    project_id, job_id, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    result = _scale(client, project_id, 0.5)
    assert result["tempo_map"][0]["bpm"] == 70.0
    assert result["ratio"] == 0.5
    assert result["at_min"] is True
    assert _midi_tempos(project_id, job_id) == [70.0]


def test_tempo_round_trip_returns_to_displayed_value(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    _scale(client, project_id, 2)
    result = _scale(client, project_id, 0.5)
    assert result["tempo_map"][0]["bpm"] == 140.0
    assert result["ratio"] == 1.0


def test_tempo_clamps_at_double_and_half(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    _scale(client, project_id, 2)
    # Already at 2x the analysis tempo: a second double is a no-op.
    result = _scale(client, project_id, 2)
    assert result["tempo_map"][0]["bpm"] == 280.0
    assert result["ratio"] == 2.0
    _scale(client, project_id, 0.5)
    _scale(client, project_id, 0.5)
    # Back through 140 to 70, then clamped at half.
    result = _scale(client, project_id, 0.5)
    assert result["tempo_map"][0]["bpm"] == 70.0
    assert result["ratio"] == 0.5


def test_tempo_undo_restores(client, monkeypatch):
    project_id, job_id, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    _scale(client, project_id, 2)
    undone = client.post(f"/api/projects/{project_id}/undo")
    assert undone.status_code == 200
    assert undone.json()["performance"]["tempo_map"][0]["bpm"] == 140.0
    assert _midi_tempos(project_id, job_id) == [140.0]


def test_tempo_multi_segment_scales_each(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [
            TempoChange(time_seconds=0, bpm=120, numerator=4, denominator=4),
            TempoChange(time_seconds=10, bpm=60, numerator=3, denominator=4),
        ],
    )
    result = _scale(client, project_id, 2)
    assert [c["bpm"] for c in result["tempo_map"]] == [240.0, 120.0]
    assert [c["time_seconds"] for c in result["tempo_map"]] == [0, 10]
    assert [c["numerator"] for c in result["tempo_map"]] == [4, 3]


def test_tempo_rejects_other_factors(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    response = client.post(f"/api/projects/{project_id}/tempo", json={"factor": 3})
    assert response.status_code == 422


def test_tempo_empty_map_defaults_to_120(client, monkeypatch):
    project_id, _, _ = _seed_project(client, monkeypatch, [])
    result = _scale(client, project_id, 2)
    assert result["tempo_map"] == [
        {"time_seconds": 0.0, "bpm": 240.0, "numerator": 4, "denominator": 4}
    ]


def test_tempo_status_endpoint(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    status = client.get(f"/api/projects/{project_id}/tempo").json()
    assert status["bpm"] == 140.0
    assert status["ratio"] == 1.0
    assert status["at_min"] is False
    assert status["at_max"] is False
    _scale(client, project_id, 2)
    status = client.get(f"/api/projects/{project_id}/tempo").json()
    assert status["ratio"] == 2.0
    assert status["at_max"] is True


def test_musicxml_export_follows_tempo(client, monkeypatch):
    project_id, _, _ = _seed_project(
        client,
        monkeypatch,
        [TempoChange(time_seconds=0, bpm=140, numerator=4, denominator=4)],
    )
    _scale(client, project_id, 2)
    exported = client.get(f"/api/projects/{project_id}/musicxml")
    assert exported.status_code == 200
    assert "<per-minute>280</per-minute>" in exported.text
