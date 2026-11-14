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

## Tempo correction (optional, Beat This!)

The stock DrumScript tempo estimator octave-errors on real songs (rock
69.8 BPM vs true ~140). When the Beat This! checkpoint is available, the
engine replaces the tempo map with the fused Beat This! tempo; otherwise
the stock tempo is kept unchanged.

```bash
pip install git+https://github.com/CPJKU/beat_this
export BEAT_THIS_CHECKPOINT=/path/to/final0.ckpt
```

The checkpoint (~81 MB, MIT) is not committed to the repo. Without it,
transcription still works — only the tempo correction is skipped.
