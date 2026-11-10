# Backend

FastAPI project API scaffold.

- `GET /api/health`: reports API health and explicitly reports that no transcription engine is configured.
- `POST /api/projects`: validates extension/size and stores an uploaded audio file locally.
- `GET /api/projects`: lists saved project metadata, newest first.
- `GET /api/projects/{project_id}/audio`: streams the original uploaded audio for reopening a project.
- `GET /api/projects/{project_id}/reference-events`: returns manually confirmed reference drum events for a project.
- `PUT /api/projects/{project_id}/reference-events`: atomically replaces the project's reference events. Each event has a positive integer `id`, non-negative finite `onset_seconds`, and one supported instrument label (`kick`, `snare`, `closed_hat`, `open_hat`, `low_tom`, `mid_tom`, `high_tom`, `crash`, or `ride`). Duplicate IDs and more than 100,000 events are rejected.
- `POST /api/projects/{project_id}/analyze`: intentionally returns 501 until an engine is integrated and validated.

Reference events are stored in the same SQLite database as their project metadata. They are human annotations only; model predictions must not be treated as ground truth. The browser UI synchronizes them to the project API after the upload project is created. The project library can list saved projects, reopen one, retrieve its original audio, and restore its reference annotations. CSV export remains available as a portable backup.

Run with Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

This is a local-development scaffold, not a production-hardened upload service. It currently has no authentication or per-user project isolation.
