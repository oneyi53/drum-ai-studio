"""Command-line entry point for reproducible canonical-event evaluation."""
from __future__ import annotations

import argparse
from pathlib import Path

from .drum_events import DrumPerformance, evaluate_performance


def evaluate_files(reference_path: Path, predicted_path: Path, tolerance_ms: float = 50.0):
    reference = DrumPerformance.model_validate_json(reference_path.read_text(encoding="utf-8"))
    predicted = DrumPerformance.model_validate_json(predicted_path.read_text(encoding="utf-8"))
    return evaluate_performance(
        reference.events,
        predicted.events,
        tolerance_ms=tolerance_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score predicted canonical drum events against a reviewed reference."
    )
    parser.add_argument("--reference", required=True, type=Path, help="Reference DrumPerformance JSON")
    parser.add_argument("--predicted", required=True, type=Path, help="Predicted DrumPerformance JSON")
    parser.add_argument("--tolerance-ms", type=float, default=50.0, help="Timing tolerance (default: 50)")
    args = parser.parse_args()

    report = evaluate_files(args.reference, args.predicted, args.tolerance_ms)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
