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
        "audio_duration_seconds": 2.0,
        "audio_sample_rate_hz": 44100,
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
    assert result["aggregate_by_split"]["evaluation"]["overall"]["f1"] == 1.0
    assert result["aggregate"]["overall"]["mean_absolute_timing_error_ms"] == pytest.approx(20)


def test_evaluate_manifest_requires_all_case_files(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"cases": [_case()]}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="audio"):
        evaluate_manifest(manifest_path)

def test_aggregate_never_matches_events_across_recordings(tmp_path):
    (tmp_path / "audio.wav").write_bytes(b"permitted test fixture")
    kick = _performance(0.5)
    empty = DrumPerformance(duration_seconds=2).model_dump_json()
    (tmp_path / "reference-a.json").write_text(kick, encoding="utf-8")
    (tmp_path / "predicted-a.json").write_text(empty, encoding="utf-8")
    (tmp_path / "reference-b.json").write_text(empty, encoding="utf-8")
    (tmp_path / "predicted-b.json").write_text(kick, encoding="utf-8")
    first = _case("case-a", "recording-a")
    second = _case("case-b", "recording-b")
    first.update(reference_path="reference-a.json", predicted_path="predicted-a.json")
    second.update(reference_path="reference-b.json", predicted_path="predicted-b.json")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"cases": [first, second]}), encoding="utf-8"
    )

    result = evaluate_manifest(manifest_path)
    overall = result["aggregate"]["overall"]
    assert overall["true_positives"] == 0
    assert overall["false_positives"] == 1
    assert overall["false_negatives"] == 1

def test_manifest_rejects_paths_outside_manifest_directory():
    case = _case()
    case["reference_path"] = "../outside.json"
    with pytest.raises(ValueError, match="relative"):
        BenchmarkManifest(cases=[case])
