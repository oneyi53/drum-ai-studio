from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DRUMAI_DATA_DIR", APP_DIR.parent.parent / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "drumai.sqlite3"
MAX_UPLOAD_BYTES = int(os.getenv("DRUMAI_MAX_UPLOAD_BYTES", 100 * 1024 * 1024))
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}

app = FastAPI(
    title="DrumAI Studio API",
    version="0.1.0",
    description="P0 API scaffold; automatic transcription is not enabled yet.",
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
    with sqlite3.connect(DB_PATH) as connection:
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


@app.on_event("startup")
def startup() -> None:
    initialize_storage()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="drumai-studio-api",
        transcription_engine="not_configured",
    )


@app.post("/api/projects")
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

        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(DB_PATH) as connection:
            connection.execute(
                """
                INSERT INTO projects
                (id, original_filename, stored_filename, size_bytes, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, audio.filename or "audio", stored_filename, size, created_at, "uploaded"),
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


@app.post("/api/projects/{project_id}/analyze")
def analyze_project(project_id: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=(
            "Transcription engine is not integrated. P0 only creates project uploads; "
            "engine compatibility and accuracy must be validated before enabling analysis."
        ),
    )
