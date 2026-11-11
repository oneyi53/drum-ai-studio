"""Project-scoped quantization endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import main as api
from .quantization import Subdivision, quantize_performance

router = APIRouter()


class QuantizeRequest(BaseModel):
    subdivision: Subdivision = "1/16"
    strength: float = Field(default=100, ge=0, le=100)
    apply: bool = True


@router.post("/api/projects/{project_id}/quantize")
def quantize_project(project_id: str, payload: QuantizeRequest) -> dict[str, Any]:
    with api.connect_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row, performance = api._load_editable_performance(connection, project_id)
        try:
            updated = quantize_performance(
                performance,
                subdivision=payload.subdivision,
                strength=payload.strength,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if payload.apply:
            api._save_edited_performance(
                connection, row["id"], row["midi_filename"], updated
            )
    return {
        "applied": payload.apply,
        "subdivision": payload.subdivision,
        "strength": payload.strength,
        "performance": updated.model_dump(),
    }
