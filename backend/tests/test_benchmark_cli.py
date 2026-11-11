import json

import pytest

from app.benchmark_cli import BenchmarkManifest, evaluate_manifest
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance


def _performance(time_seconds: float) -> str:
    return DrumPerformance(
        duration_seconds=2,
        events=[DrumEvent(time_seconds=time_seconds, instrument=DrumInstrument.KICK)],
    ).model_dump_json()


def _case(case_id="take-01", source="recording-01", split="evaluation"):
    return {
        "id": case_id,
        "source_recording_id": source,
        "split": split,
        "audio_path": "audio.wav",
        "reference_path": "reference.json",
        "predicted_path": "predicted.json",
        "permission_basis": "written_permission",
        "annotation_status": "reviewed",
        "reviewer": "reviewer-1",
        "annotation_revision": "v1",
    }


def test_manifest_rejects_source_recording_split_leakage():
    with pytest.raises(ValueError, match="multiple splits"):
        BenchmarkManifest(cases=[
            _case("dev", "same-recording", "development"),
            _case("eval", "same-recording", "evaluation"),
        ])


def test_manifest_rejects_unreviewed_or_unpermissioned_cases():
    case = _case()
    case["annotation_status"] = "draft"
    with pytest.raises(ValueError):
        BenchmarkManifest(cases=[case])
    case = _case()
    case["permission_basis"] = "unknown"
    with pytest.raises(ValueError):
        BenchmarkManifest(cases=[case])


def test_evaluate_manifest_scores_reviewed_case_and_aggregate(tmp_path):
    (tmp_path / "audio.wav").write_bytes(b"permitted test fixture")
    (tmp_path / "reference.json").write_text(_performance(0.5), encoding="utf-8")
    (tmp_path / "predicted.json").write_text(_performance(0.52), encoding="utf-8")
    manifest = {"schema_version": "1.0", "cases": [_case()]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = evaluate_manifest(manifest_path)
    assert result["case_count"] == 1
    assert result["cases"][0]["metrics"]["overall"]["f1"] == 1.0
    assert result["aggregate"]["overall"]["mean_absolute_timing_error_ms"] == pytest.approx(20)


def test_evaluate_manifest_requires_all_case_files(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"cases": [_case()]}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="audio"):
        evaluate_manifest(manifest_path)
