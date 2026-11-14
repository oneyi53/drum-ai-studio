"""Re-editable JSON project file (.drumai.json) and annotation CSV export.

The project file is the re-editable carrier for a drum-ai-studio project
(the天津谱 .tjp equivalent): it holds the audio reference, the full
canonical event list, the tempo map, the edit-history revision it was
exported from, and the ground-truth annotation state. It contains no audio
bytes — the audio stays in the project it was exported from.
"""
from __future__ import annotations

import csv
import io
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .drum_events import DrumEvent, DrumPerformance, TempoChange

PROJECT_FILE_FORMAT = "drumai-project"
PROJECT_FILE_VERSION = "1.0"

# Instrument labels the evaluation harness (scripts/evaluate_midi.py)
# accepts as canonical reference names. The app's native closed_hihat /
# open_hihat are aliased there, but the exported benchmark uses the
# canonical labels directly so the file is self-explanatory.
EVALUATOR_INSTRUMENT_LABELS = {
    "closed_hihat": "closed_hat",
    "open_hihat": "open_hat",
}


class ProjectFileAudio(BaseModel):
    """Which audio this file belongs to. Import only accepts a file whose
    audio matches the target project (same project id and filename)."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)


class ProjectFileAnnotation(BaseModel):
    """Ground-truth annotation state, carried in the file so a half-done
    annotation can be exported, handed over, and resumed later."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_started", "in_progress", "done"] = "not_started"
    done_bars: list[int] = Field(default_factory=list)
    note: str = ""


class ProjectFile(BaseModel):
    """The .drumai.json document. Extra fields are rejected so a file from
    another tool cannot smuggle in unvalidated content."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["drumai-project"] = PROJECT_FILE_FORMAT
    version: Literal["1.0"] = PROJECT_FILE_VERSION
    audio: ProjectFileAudio
    duration_seconds: float = Field(gt=0)
    tempo_map: list[TempoChange] = Field(default_factory=list)
    events: list[DrumEvent] = Field(default_factory=list)
    history_revision: int = Field(ge=0)
    annotation: ProjectFileAnnotation = Field(default_factory=ProjectFileAnnotation)

    def to_performance(self) -> DrumPerformance:
        """The canonical performance this file describes. Validation runs
        again here, so a hand-edited file cannot inject out-of-range
        events or a disordered tempo map."""
        return DrumPerformance(
            duration_seconds=self.duration_seconds,
            events=self.events,
            tempo_map=self.tempo_map,
        )


class ProjectFileExportRequest(BaseModel):
    """Optional annotation state to stamp into an exported file. The
    editor owns the live annotation state; the file is its carrier."""

    model_config = ConfigDict(extra="forbid")

    annotation: ProjectFileAnnotation = Field(default_factory=ProjectFileAnnotation)


def build_project_file(
    project_id: str,
    original_filename: str,
    performance: DrumPerformance,
    history_revision: int,
    annotation: ProjectFileAnnotation | None = None,
) -> ProjectFile:
    return ProjectFile(
        audio=ProjectFileAudio(
            project_id=project_id, original_filename=original_filename
        ),
        duration_seconds=performance.duration_seconds,
        tempo_map=performance.tempo_map,
        events=performance.events,
        history_revision=history_revision,
        annotation=annotation or ProjectFileAnnotation(),
    )


def annotation_csv_text(performance: DrumPerformance) -> str:
    """Reference CSV in the format scripts/evaluate_midi.py accepts:
    ``onset_seconds,instrument`` — one row per event, sorted by onset,
    with the evaluator's canonical instrument labels. This is the
    corrected set: whatever the editor currently holds is the reference.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["onset_seconds", "instrument"])
    for event in sorted(performance.events, key=lambda item: item.time_seconds):
        label = EVALUATOR_INSTRUMENT_LABELS.get(
            event.instrument.value, event.instrument.value
        )
        writer.writerow([f"{event.time_seconds:.3f}", label])
    return buffer.getvalue()
