import json

from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance
from app.evaluate_cli import evaluate_files


def test_evaluate_files_reads_canonical_performance_json(tmp_path):
    reference = DrumPerformance(
        duration_seconds=2,
        events=[DrumEvent(time_seconds=0.5, instrument=DrumInstrument.KICK)],
    )
    predicted = DrumPerformance(
        duration_seconds=2,
        events=[DrumEvent(time_seconds=0.52, instrument=DrumInstrument.KICK)],
    )
    reference_path = tmp_path / "reference.json"
    predicted_path = tmp_path / "predicted.json"
    reference_path.write_text(reference.model_dump_json(), encoding="utf-8")
    predicted_path.write_text(predicted.model_dump_json(), encoding="utf-8")

    report = evaluate_files(reference_path, predicted_path)
    assert report.overall.f1 == 1.0
    assert report.overall.mean_absolute_timing_error_ms == 20.000000000000018
