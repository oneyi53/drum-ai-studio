from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from threading import Lock
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine_adapter import DrumScriptEngine

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DRUMAI_DATA_DIR", APP_DIR.parent.parent / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = DATA_DIR / "drumai.sqlite3"
MAX_UPLOAD_BYTES = int(os.getenv("DRUMAI_MAX_UPLOAD_BYTES", 100 * 1024 * 1024))
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
ENGINE_LOCK = Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
async def create_project(audio: UploadFile = File(...)) -> dict[str, str | int]:
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
    except Exception as exc:
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
