# Backend

FastAPI project API scaffold.

- `GET /api/health`: reports API health and the configured engine runtime.
- `POST /api/projects`: validates extension/size and stores an uploaded audio file locally.
- `GET /api/projects`: lists saved projects, newest first, with the latest analysis state.
- `GET /api/projects/{project_id}/audio`: streams the original uploaded audio for reopening a project.
- `DELETE /api/projects/{project_id}`: removes a project, its files, and its database records (refused while an analysis job is active).
- `POST /api/projects/{project_id}/analyze`: runs asynchronous DrumScript analysis (HTTP 202 with a job id) when the engine runtime is configured.
- `GET /api/projects/{project_id}/musicxml`, `/pdf`, `/midi`, `/bundle`: export the current performance from the same canonical events used by the editor.

Run with Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

This is a local-development scaffold, not a production-hardened upload service.
