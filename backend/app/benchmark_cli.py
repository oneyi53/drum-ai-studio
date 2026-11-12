"""Batch evaluation for permission-cleared, reviewed benchmark cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .drum_events import DrumPerformance, evaluate_performance


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source_recording_id: str = Field(min_length=1)
    split: Literal["development", "evaluation"]
    audio_path: str = Field(min_length=1)
    audio_duration_seconds: float = Field(gt=0)
    audio_sample_rate_hz: int = Field(gt=0)
    reference_path: str = Field(min_length=1)
    predicted_path: str = Field(min_length=1)
    permission_basis: Literal["public_domain", "licensed", "written_permission"]
    annotation_status: Literal["reviewed"]
    reviewer: str = Field(min_length=1)
    annotation_revision: str = Field(min_length=1)

    @field_validator("audio_path", "reference_path", "predicted_path")
    @classmethod
    def paths_must_stay_within_manifest_directory(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("benchmark paths must be relative and cannot escape the manifest directory")
        return value


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    cases: list[BenchmarkCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_identity_and_splits(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case ids must be unique")
        splits: dict[str, set[str]] = {}
        for case in self.cases:
            splits.setdefault(case.source_recording_id, set()).add(case.split)
        leaked = sorted(source_id for source_id, values in splits.items() if len(values) > 1)
        if leaked:
            raise ValueError(
                "source recordings cannot appear in multiple splits: " + ", ".join(leaked)
            )
        return self


def evaluate_manifest(manifest_path: Path, tolerance_ms: float = 50.0) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = BenchmarkManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if not manifest.cases:
        raise ValueError("benchmark manifest contains no cases")
    root = manifest_path.parent
    case_reports = []
    all_reference = []
    all_predicted = []
    timeline_offset = 0.0
    split_reference = {"development": [], "evaluation": []}
    split_predicted = {"development": [], "evaluation": []}
    for case in manifest.cases:
        paths = {
            "audio": root / case.audio_path,
            "reference": root / case.reference_path,
            "predicted": root / case.predicted_path,
        }
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"case {case.id!r} is missing required file(s): {', '.join(missing)}"
            )
        reference = DrumPerformance.model_validate_json(
            paths["reference"].read_text(encoding="utf-8")
        )
        predicted = DrumPerformance.model_validate_json(
            paths["predicted"].read_text(encoding="utf-8")
        )
        report = evaluate_performance(
            reference.events, predicted.events, tolerance_ms=tolerance_ms
        )
        case_reports.append({
            "id": case.id,
            "source_recording_id": case.source_recording_id,
            "split": case.split,
            "permission_basis": case.permission_basis,
            "annotation_revision": case.annotation_revision,
            "metrics": report.model_dump(),
        })
        # Keep cases on disjoint timelines so equal timestamps in different
        # recordings can never be matched to each other in the pooled report.
        shifted_reference = [
            event.model_copy(update={"time_seconds": event.time_seconds + timeline_offset})
            for event in reference.events
        ]
        shifted_predicted = [
            event.model_copy(update={"time_seconds": event.time_seconds + timeline_offset})
            for event in predicted.events
        ]
        all_reference.extend(shifted_reference)
        all_predicted.extend(shifted_predicted)
        split_reference[case.split].extend(shifted_reference)
        split_predicted[case.split].extend(shifted_predicted)
        timeline_offset += max(reference.duration_seconds, predicted.duration_seconds) + max(1.0, tolerance_ms / 1000 + 0.001)

    aggregate = evaluate_performance(
        all_reference, all_predicted, tolerance_ms=tolerance_ms
    )
    aggregate_by_split = {
        split: evaluate_performance(
            split_reference[split],
            split_predicted[split],
            tolerance_ms=tolerance_ms,
        ).model_dump()
        for split in ("development", "evaluation")
        if any(case.split == split for case in manifest.cases)
    }
    return {
        "schema_version": "1.0",
        "manifest": manifest_path.name,
        "tolerance_ms": tolerance_ms,
        "case_count": len(case_reports),
        "cases": case_reports,
        "aggregate": aggregate.model_dump(),
        "aggregate_by_split": aggregate_by_split,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-score predictions against reviewed drum-event references."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    args = parser.parse_args()
    print(json.dumps(
        evaluate_manifest(args.manifest, args.tolerance_ms),
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
