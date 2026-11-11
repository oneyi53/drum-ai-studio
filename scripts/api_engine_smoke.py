from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from engine_smoke import make_synthetic_full_mix  # noqa: E402

with tempfile.TemporaryDirectory(prefix="drumai-api-e2e-") as data_dir:
    os.environ["DRUMAI_DATA_DIR"] = data_dir
    from app.main import app  # noqa: E402

    audio_path = Path(data_dir) / "synthetic_full_mix.wav"
    make_synthetic_full_mix(audio_path)

    with TestClient(app) as client:
        with audio_path.open("rb") as audio_file:
            uploaded = client.post(
                "/api/projects",
                files={"audio": ("synthetic_full_mix.wav", audio_file, "audio/wav")},
            )
        if uploaded.status_code != 201:
            raise RuntimeError(f"API upload failed: {uploaded.status_code} {uploaded.text}")
        project_id = uploaded.json()["id"]

        started = client.post(f"/api/projects/{project_id}/analyze")
        if started.status_code != 202:
            raise RuntimeError(f"API job creation failed: {started.status_code} {started.text}")
        job_id = started.json()["job_id"]

        job = client.get(f"/api/analysis-jobs/{job_id}")
        job_data = job.json()
        if job.status_code != 200 or job_data.get("status") != "completed":
            raise RuntimeError(f"API engine job did not complete: {job_data}")

        result = client.get(f"/api/projects/{project_id}/performance")
        if result.status_code != 200:
            raise RuntimeError(f"Canonical result fetch failed: {result.status_code} {result.text}")
        performance = result.json()["performance"]
        events = performance.get("events", [])
        if not events:
            raise RuntimeError("API completed but returned no canonical drum events")

        midi = client.get(f"/api/projects/{project_id}/midi")
        if midi.status_code != 200 or not midi.content:
            raise RuntimeError("API did not return a non-empty generated MIDI download")

        print(
            "API_ENGINE_E2E_OK "
            f"job_id={job_id} events={len(events)} "
            f"duration_seconds={performance['duration_seconds']:.3f} "
            f"midi_bytes={len(midi.content)}"
        )
