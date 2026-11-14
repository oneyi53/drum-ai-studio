from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_prediction_csv import audit_csv


def write_events(path: Path, rows: list[dict]) -> None:
    fields = ["onset_seconds", "instrument", "pitch", "velocity", "duration_seconds"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_audit_flags_constant_velocity_duration_and_duplicate_hits(tmp_path: Path) -> None:
    path = tmp_path / "prediction.csv"
    write_events(path, [
        {"onset_seconds": "0.0", "instrument": "kick", "pitch": 36, "velocity": 100, "duration_seconds": "0.1"},
        {"onset_seconds": "0.0", "instrument": "kick", "pitch": 36, "velocity": 100, "duration_seconds": "0.1"},
        {"onset_seconds": "1.0", "instrument": "snare", "pitch": 38, "velocity": 100, "duration_seconds": "0.1"},
    ])

    report = audit_csv(path)
    assert report["event_count"] == 3
    assert report["same_onset_same_instrument_duplicate_groups"] == [
        {"onset_seconds": 0.0, "instrument": "kick", "count": 2}
    ]
    assert any("same velocity" in warning for warning in report["warnings"])
    assert any("same duration" in warning for warning in report["warnings"])


def test_audit_rejects_non_finite_onset(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    write_events(path, [
        {"onset_seconds": "nan", "instrument": "kick", "pitch": 36, "velocity": 100, "duration_seconds": "0.1"},
    ])
    with pytest.raises(ValueError, match="onset_seconds"):
        audit_csv(path)


def test_audit_reports_empty_time_bins(tmp_path: Path) -> None:
    path = tmp_path / "gaps.csv"
    write_events(path, [
        {"onset_seconds": "0.2", "instrument": "kick", "pitch": 36, "velocity": 80, "duration_seconds": "0.1"},
        {"onset_seconds": "25.2", "instrument": "snare", "pitch": 38, "velocity": 90, "duration_seconds": "0.1"},
    ])
    report = audit_csv(path, bin_seconds=10)
    assert report["empty_time_bins_seconds"] == [10.0]
