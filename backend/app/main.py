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
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .drum_events import DrumEvent, DrumInstrument, DrumPerformance
from .engine_adapter import DrumScriptEngine
from .midi_adapter import performance_to_midi
from .musicxml_adapter import performance_to_musicxml
from .quantization_api import router as quantization_router

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

app.include_router(quantization_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "DRUMAI_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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


class EventBatchRequest(BaseModel):
    event_ids: list[str] = Field(min_length=1, max_length=5000)
    time_offset_seconds: float | None = None


class EventDuplicateRequest(BaseModel):
    event_ids: list[str] = Field(min_length=1, max_length=5000)
    repeat_count: int = Field(default=1, ge=1, le=16)
    interval_seconds: float = Field(gt=0)



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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_revisions (
                project_id TEXT NOT NULL REFERENCES projects(id),
                revision INTEGER NOT NULL,
                performance_json TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (project_id, revision)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_history_state (
                project_id TEXT PRIMARY KEY REFERENCES projects(id),
                current_revision INTEGER NOT NULL
            )
            """
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


@app.get("/api/projects")
def list_projects(limit: int = 20) -> dict[str, list[dict[str, Any]]]:
    """List recent local projects and the latest analysis state for each."""
    bounded_limit = max(1, min(limit, 100))
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT
                projects.id,
                projects.original_filename,
                projects.size_bytes,
                projects.created_at,
                projects.status,
                jobs.id AS latest_job_id,
                jobs.status AS latest_job_status
            FROM projects
            LEFT JOIN analysis_jobs AS jobs
              ON jobs.id = (
                  SELECT id FROM analysis_jobs
                  WHERE project_id=projects.id
                  ORDER BY created_at DESC LIMIT 1
              )
            ORDER BY projects.created_at DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return {"projects": [dict(row) for row in rows]}


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
                """
                INSERT OR IGNORE INTO performance_revisions
                (project_id, revision, performance_json, action, created_at)
                VALUES (?, 0, ?, 'analysis', ?)
                """,
                (job["project_id"], performance.model_dump_json(), utc_now()),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO performance_history_state (project_id, current_revision)
                VALUES (?, 0)
                """,
                (job["project_id"],),
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


@app.get("/api/projects/{project_id}/audio")
def get_project_audio(project_id: str) -> FileResponse:
    """Stream the original uploaded audio for playback and timeline synchronization."""
    with connect_db() as connection:
        project = connection.execute(
            "SELECT stored_filename, original_filename FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    stored_filename = project["stored_filename"]
    # Only use the server-generated basename stored in SQLite.
    audio_path = (UPLOAD_DIR / stored_filename).resolve()
    if audio_path.parent != UPLOAD_DIR.resolve() or not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded audio file is missing.")
    import mimetypes

    media_type = mimetypes.guess_type(project["original_filename"])[0] or "application/octet-stream"
    return FileResponse(
        audio_path,
        media_type=media_type,
        filename=Path(project["original_filename"]).name,
        content_disposition_type="inline",
    )


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
    project = connection.execute(
        "SELECT project_id, performance_json FROM analysis_jobs WHERE id=?", (job_id,)
    ).fetchone()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    project_id = project["project_id"]
    current = connection.execute(
        "SELECT current_revision FROM performance_history_state WHERE project_id=?",
        (project_id,),
    ).fetchone()
    if current is None:
        connection.execute(
            """
            INSERT INTO performance_revisions
            (project_id, revision, performance_json, action, created_at)
            VALUES (?, 0, ?, 'analysis', ?)
            """,
            (project_id, project["performance_json"] or performance.model_dump_json(), utc_now()),
        )
        connection.execute(
            "INSERT INTO performance_history_state (project_id, current_revision) VALUES (?, 0)",
            (project_id,),
        )
        current_revision = 0
    else:
        current_revision = current["current_revision"]
    next_revision = current_revision + 1
    connection.execute(
        "DELETE FROM performance_revisions WHERE project_id=? AND revision>?",
        (project_id, current_revision),
    )
    connection.execute(
        """
        INSERT INTO performance_revisions
        (project_id, revision, performance_json, action, created_at)
        VALUES (?, ?, ?, 'edit', ?)
        """,
        (project_id, next_revision, performance.model_dump_json(), utc_now()),
    )
    connection.execute(
        "UPDATE performance_history_state SET current_revision=? WHERE project_id=?",
        (next_revision, project_id),
    )
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



@app.post("/api/projects/{project_id}/events/duplicate")
def duplicate_events(project_id: str, payload: EventDuplicateRequest) -> dict[str, Any]:
    if len(set(payload.event_ids)) != len(payload.event_ids):
        raise HTTPException(status_code=422, detail="event_ids must be unique.")
    selected = set(payload.event_ids)
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        originals = [event for event in performance.events if event.id in selected]
        if len(originals) != len(selected):
            raise HTTPException(status_code=404, detail="One or more drum events were not found.")
        duplicates: list[DrumEvent] = []
        for repeat in range(1, payload.repeat_count + 1):
            offset = payload.interval_seconds * repeat
            for event in originals:
                clone_data = event.model_dump()
                clone_data.update({
                    "id": str(uuid.uuid4()),
                    "time_seconds": event.time_seconds + offset,
                    "source": "manual",
                    "manually_corrected": True,
                })
                duplicates.append(DrumEvent.model_validate(clone_data))
        if any(event.time_seconds > performance.duration_seconds for event in duplicates):
            raise HTTPException(
                status_code=422,
                detail="Duplicated events must remain within the song duration.",
            )
        try:
            updated = DrumPerformance.model_validate({
                **performance.model_dump(),
                "events": [*performance.events, *duplicates],
            })
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {
        "duplicated_count": len(duplicates),
        "events": [event.model_dump() for event in duplicates],
        "performance": updated.model_dump(),
    }


@app.patch("/api/projects/{project_id}/events/batch")
def batch_update_events(project_id: str, payload: EventBatchRequest) -> dict[str, Any]:
    if payload.time_offset_seconds is None:
        raise HTTPException(status_code=422, detail="time_offset_seconds must be provided.")
    if len(set(payload.event_ids)) != len(payload.event_ids):
        raise HTTPException(status_code=422, detail="event_ids must be unique.")
    selected = set(payload.event_ids)
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        found = {event.id for event in performance.events if event.id in selected}
        if found != selected:
            raise HTTPException(status_code=404, detail="One or more drum events were not found.")
        events = [
            event.model_copy(update={
                "time_seconds": event.time_seconds + payload.time_offset_seconds,
                "source": "manual",
                "manually_corrected": True,
            }) if event.id in selected else event
            for event in performance.events
        ]
        if any(event.time_seconds < 0 for event in events):
            raise HTTPException(
                status_code=422,
                detail="A batch time shift cannot move drum events before time zero.",
            )
        try:
            updated = DrumPerformance.model_validate({**performance.model_dump(), "events": events})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {"updated_event_ids": payload.event_ids, "performance": updated.model_dump()}


@app.delete("/api/projects/{project_id}/events/batch")
def batch_delete_events(project_id: str, payload: EventBatchRequest) -> dict[str, Any]:
    if len(set(payload.event_ids)) != len(payload.event_ids):
        raise HTTPException(status_code=422, detail="event_ids must be unique.")
    selected = set(payload.event_ids)
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = _load_editable_performance(connection, project_id)
        found = {event.id for event in performance.events if event.id in selected}
        if found != selected:
            raise HTTPException(status_code=404, detail="One or more drum events were not found.")
        updated = DrumPerformance.model_validate({
            **performance.model_dump(),
            "events": [event for event in performance.events if event.id not in selected],
        })
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {"deleted_event_ids": payload.event_ids, "performance": updated.model_dump()}



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
        _save_edited_performance(connection, row["id"], row["midi_filename"], updated)
    return {"deleted_event_id": event_id, "performance": updated.model_dump()}




def _history_status(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    state = connection.execute(
        "SELECT current_revision FROM performance_history_state WHERE project_id=?",
        (project_id,),
    ).fetchone()
    if state is None:
        return {"current_revision": 0, "can_undo": False, "can_redo": False}
    current = state["current_revision"]
    bounds = connection.execute(
        "SELECT MIN(revision) AS first_revision, MAX(revision) AS last_revision "
        "FROM performance_revisions WHERE project_id=?",
        (project_id,),
    ).fetchone()
    return {
        "current_revision": current,
        "can_undo": bounds["first_revision"] is not None and current > bounds["first_revision"],
        "can_redo": bounds["last_revision"] is not None and current < bounds["last_revision"],
    }


@app.get("/api/projects/{project_id}/history")
def get_project_history(project_id: str) -> dict[str, Any]:
    with connect_db() as connection:
        exists = connection.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return _history_status(connection, project_id)


def _save_edited_performance_without_history(
    connection: sqlite3.Connection,
    job_id: str,
    midi_filename: str,
    performance: DrumPerformance,
) -> None:
    midi_path = ANALYSIS_DIR / job_id / midi_filename
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


def _move_history(project_id: str, direction: int) -> dict[str, Any]:
    with connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, _ = _load_editable_performance(connection, project_id)
        state = connection.execute(
            "SELECT current_revision FROM performance_history_state WHERE project_id=?",
            (project_id,),
        ).fetchone()
        if state is None:
            raise HTTPException(status_code=409, detail="No edit history is available.")
        target = state["current_revision"] + direction
        revision = connection.execute(
            "SELECT performance_json FROM performance_revisions WHERE project_id=? AND revision=?",
            (project_id, target),
        ).fetchone()
        if revision is None:
            raise HTTPException(status_code=409, detail="No further undo/redo action is available.")
        restored = DrumPerformance.model_validate_json(revision["performance_json"])
        _save_edited_performance_without_history(
            connection, row["id"], row["midi_filename"], restored
        )
        connection.execute(
            "UPDATE performance_history_state SET current_revision=? WHERE project_id=?",
            (target, project_id),
        )
        history = _history_status(connection, project_id)
    return {"performance": restored.model_dump(), **history}


@app.post("/api/projects/{project_id}/undo")
def undo_project_edit(project_id: str) -> dict[str, Any]:
    return _move_history(project_id, -1)


@app.post("/api/projects/{project_id}/redo")
def redo_project_edit(project_id: str) -> dict[str, Any]:
    return _move_history(project_id, 1)


@app.get("/api/projects/{project_id}/musicxml")
def download_project_musicxml(project_id: str) -> Response:
    """Export the latest canonical performance as an editable MusicXML drum score."""
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT performance_json
            FROM analysis_jobs
            WHERE project_id=? AND status='completed' AND performance_json IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No completed performance is available.")
    performance = DrumPerformance.model_validate_json(row["performance_json"])
    return Response(
        content=performance_to_musicxml(performance),
        media_type="application/vnd.recordare.musicxml+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{project_id}-drums.musicxml"'
        },
    )


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

