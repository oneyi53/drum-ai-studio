# Backend

FastAPI project API scaffold.

- `GET /api/health`: reports API health and explicitly reports that no transcription engine is configured.
- `POST /api/projects`: validates extension/size and stores an uploaded audio file locally.
- `POST /api/projects/{project_id}/analyze`: intentionally returns 501 until an engine is integrated and validated.

Run with Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

This is a local-development scaffold, not a production-hardened upload service.
