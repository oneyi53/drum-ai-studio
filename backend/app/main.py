from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .drum_events import DrumEvent, DrumInstrument, DrumPerformance
from .engine_adapter import DrumScriptEngine
from .midi_adapter import performance_to_midi

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DRUMAI_DATA_DIR", APP_DIR.parent.parent / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = DATA_DIR / "drumai.sqlite3"
MAX_UPLOAD_BYTES = int(os.getenv("DRUMAI_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
ENGINE_LOCK = Lock()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


app = FastAPI(
    title="DrumAI Studio API",
    version="0.2.0",
    description="Audio upload and asynchronous DrumScript analysis API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "DRUMAI_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    transcription_engine: str


class EventCreateRequest(BaseModel):
    time_seconds: float = Field(ge=0)
    instrument: DrumInstrument
    velocity: int = Field(default=96, ge=1, le=127)


class EventUpdateRequest(BaseModel):
    time_seconds: float | None = Field(default=None, ge=0)
    instrument: DrumInstrument | None = None
    velocity: int | None = Field(default=None, ge=1, le=127)


def initialize_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT,
                midi_filename TEXT,
                performance_json TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_jobs_project ON analysis_jobs(project_id, created_at)"
        )
        now = utc_now()
        connection.execute(
            """
            UPDATE analysis_jobs
            SET status='failed', updated_at=?,
                error_message='API worker restarted before analysis completed'
            WHERE status IN ('queued', 'running')
            """,
            (now,),
        )
        connection.execute(
            "UPDATE projects SET status='failed' WHERE status='processing'"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_jobs_single_active
            ON analysis_jobs(project_id)
            WHERE status IN ('queued', 'running')
            """
        )


@app.on_event("startup")
def startup() -> None:
    initialize_storage()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        engine_installed = importlib.util.find_spec("drumscript") is not None
    except (ImportError, ValueError):
        engine_installed = False
    return HealthResponse(
        status="ok",
        service="drumai-studio-api",
        transcription_engine="available" if engine_installed else "not_installed",
    )


@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
async def create_project(audio: UploadFile = File(...)) -> dict[str, str | int]:  # noqa: B008
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio extension. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    project_id = str(uuid.uuid4())
    stored_filename = f"{project_id}{suffix}"
    destination = UPLOAD_DIR / stored_filename
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Audio file exceeds upload limit.")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO projects
                (id, original_filename, stored_filename, size_bytes, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, audio.filename or "audio", stored_filename, size, utc_now(), "uploaded"),
            )
        return {
            "id": project_id,
            "filename": audio.filename or "audio",
            "size_bytes": size,
            "status": "uploaded",
        }
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await audio.close()


def run_analysis_job(job_id: str) -> None:
    """Execute one job and persist the canonical performance or a failure."""
    with connect_db() as connection:
        job = connection.execute(
            """
            SELECT jobs.id, jobs.project_id, projects.stored_filename
            FROM analysis_jobs AS jobs
            JOIN projects ON projects.id = jobs.project_id
            WHERE jobs.id=?
            """,
            (job_id,),
        ).fetchone()
        if job is None:
            return
        connection.execute(
            "UPDATE analysis_jobs SET status='running', updated_at=? WHERE id=?",
            (utc_now(), job_id),
        )
        connection.execute(
            "UPDATE projects SET status='processing' WHERE id=?",
            (job["project_id"],),
        )

    try:
        audio_path = UPLOAD_DIR / job["stored_filename"]
        output_dir = ANALYSIS_DIR / job_id
        # Keep one in-process model inference active to avoid duplicate model
        # loads and unbounded CPU/RAM contention in the single-worker setup.
        with ENGINE_LOCK:
            performance, midi_path = DrumScriptEngine().analyze(audio_path, output_dir)
        with connect_db() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status='completed', updated_at=?, error_message=NULL,
                    midi_filename=?, performance_json=?
                WHERE id=?
                """,
                (utc_now(), midi_path.name, performance.model_dump_json(), job_id),
            )
            connection.execute(
                "UPDATE projects SET status='analyzed' WHERE id=?",
                (job["project_id"],),
            )
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {str(exc)[:500]}"
        with connect_db() as connection:
            connection.execute(
                "UPDATE analysis_jobs SET status='failed', updated_at=?, error_message=? WHERE id=?",
                (utc_now(), message, job_id),
            )
            connection.execute(
                "UPDATE projects SET status='failed' WHERE id=?",
                (job["project_id"],),
            )


@app.post("/api/projects/{project_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_project(
    project_id: str, background_tasks: BackgroundTasks
) -> dict[str, str]:
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        project = connection.execute(
            "SELECT id FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        active = connection.execute(
            """
            SELECT id FROM analysis_jobs
            WHERE project_id=? AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if active:
            raise HTTPException(
                status_code=409,
                detail={"message": "An analysis job is already active.", "job_id": active["id"]},
            )
        job_id = str(uuid.uuid4())
        now = utc_now()
        connection.execute(
            """
            INSERT INTO analysis_jobs (id, project_id, status, created_at, updated_at)
            VALUES (?, ?, 'queued', ?, ?)
            """,
            (job_id, project_id, now, now),
        )
        connection.execute("UPDATE projects SET status='queued' WHERE id=?", (project_id,))

    background_tasks.add_task(run_analysis_job, job_id)
    return {"job_id": job_id, "project_id": project_id, "status": "queued"}


@app.get("/api/analysis-jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict[str, Any]:
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, project_id, status, created_at, updated_at, error_message
            FROM analysis_jobs WHERE id=?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return dict(row)


@app.get("/api/projects/{project_id}/performance")
def get_project_performance(project_id: str) -> dict[str, Any]:
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, status, performance_json, midi_filename
            FROM analysis_jobs
            WHERE project_id=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if row is None or row["status"] != "completed" or not row["performance_json"]:
        raise HTTPException(status_code=404, detail="No completed performance is available.")
    return {
        "job_id": row["id"],
        "status": row["status"],
        "performance": json.loads(row["performance_json"]),
        "midi_filename": row["midi_filename"],
    }


def _load_editable_performance(connection: sqlite3.Connection, project_id: str):
    row = connection.execute(
        """
        SELECT id, performance_json, midi_filename
        FROM analysis_jobs
        WHERE project_id=? AND status='completed' AND performance_json IS NOT NULL
        ORDER BY created_at DESC LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No completed performance is available.")
    if not row["midi_filename"]:
        raise HTTPException(status_code=404, detail="Generated MIDI file is missing.")
    return row, DrumPerformance.model_validate_json(row["performance_json"])


def _save_edited_performance(
    connection: sqlite3.Connection,
    job_id: str,
    midi_filename: str,
    performance: DrumPerformance,
) -> None:
    midi_path = ANALYSIS_DIR / job_id / midi_filename
    if not midi_path.is_file():
        raise HTTPException(status_code=404, detail="Generated MIDI file is missing.")
    temporary_path = midi_path.with_suffix(".tmp.mid")
    try:
        performance_to_midi(performance, temporary_path)
        temporary_path.replace(midi_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    connection.execute(
        "UPDATE analysis_jobs SET performance_json=?, updated_at=? WHERE id=?",
        (performance.model_dump_json(), utc_now(), job_id),
    )


@app.post("/api/projects/{project_id}/events", status_code=status.HTTP_201_CREATED)
def add_manual_event(project_id: str, payload: EventCreateRequest) -> dict[str, Any]:
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        event = DrumEvent(
            time_seconds=payload.time_seconds,
            instrument=payload.instrument,
            velocity=payload.velocity,
            source="manual",
            manually_corrected=True,
        )
        try:
            updated = DrumPerformance.model_validate(
                {**performance.model_dump(), "events": [*performance.events, event]}
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {"event": event.model_dump(), "performance": updated.model_dump()}


@app.patch("/api/projects/{project_id}/events/{event_id}")
def update_manual_event(
    project_id: str, event_id: str, payload: EventUpdateRequest
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one event field must be provided.")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Event fields cannot be null.")
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        events = []
        found = False
        for event in performance.events:
            if event.id == event_id:
                found = True
                events.append(
                    event.model_copy(
                        update={**changes, "source": "manual", "manually_corrected": True}
                    )
                )
            else:
                events.append(event)
        if not found:
            raise HTTPException(status_code=404, detail="Drum event not found.")
        try:
            updated = DrumPerformance.model_validate(
                {**performance.model_dump(), "events": events}
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {
        "event": next(event.model_dump() for event in updated.events if event.id == event_id),
        "performance": updated.model_dump(),
    }


@app.delete("/api/projects/{project_id}/events/{event_id}")
def delete_manual_event(project_id: str, event_id: str) -> dict[str, Any]:
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        events = [event for event in performance.events if event.id != event_id]
        if len(events) == len(performance.events):
            raise HTTPException(status_code=404, detail="Drum event not found.")
        updated = DrumPerformance.model_validate(
            {**performance.model_dump(), "events": events}
        )
        _save_edited_performance(connection, row["id"], updated)
    return {"deleted_event_id": event_id, "performance": updated.model_dump()}


@app.get("/api/projects/{project_id}/midi")
def download_project_midi(project_id: str) -> FileResponse:
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT id, midi_filename
            FROM analysis_jobs
            WHERE project_id=? AND status='completed'
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if row is None or not row["midi_filename"]:
        raise HTTPException(status_code=404, detail="No completed MIDI export is available.")
    filename = row["midi_filename"]
    if Path(filename).name != filename:
        raise HTTPException(status_code=500, detail="Stored MIDI filename is invalid.")
    midi_path = ANALYSIS_DIR / row["id"] / filename
    if not midi_path.is_file():
        raise HTTPException(status_code=404, detail="Generated MIDI file is missing.")
    return FileResponse(
        path=midi_path,
        media_type="audio/midi",
        filename=f"{project_id}-drums.mid",
    )
