#!/usr/bin/env python3
"""Compare a DrumScript MIDI prediction with a manually annotated CSV reference.

Reference CSV columns:
    onset_seconds,instrument
Optional columns such as velocity are ignored.

The evaluator uses one-to-one nearest-onset matching within a configurable
tolerance. Instrument names use the normalized labels in GM_DRUM_MAP below.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

GM_DRUM_MAP = {
    35: "kick", 36: "kick",
    38: "snare", 40: "snare",
    42: "closed_hat", 44: "closed_hat",
    46: "open_hat",
    43: "low_tom", 45: "low_tom",
    47: "mid_tom", 48: "mid_tom",
    50: "high_tom",
    49: "crash", 57: "crash",
    51: "ride", 59: "ride",
}


@dataclass(frozen=True, order=True)
class Event:
    onset_seconds: float
    instrument: str


def normalize_instrument(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "bass_drum": "kick",
        "bd": "kick",
        "snare_drum": "snare",
        "hat": "closed_hat",
        "hihat": "closed_hat",
        "hi_hat": "closed_hat",
        "closed_hihat": "closed_hat",
        "open_hihat": "open_hat",
        "tom_low": "low_tom",
        "tom_mid": "mid_tom",
        "tom_high": "high_tom",
    }
    return aliases.get(normalized, normalized)


def load_reference(path: Path) -> list[Event]:
    events: list[Event] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"onset_seconds", "instrument"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Reference CSV must contain onset_seconds,instrument columns")
        for line_number, row in enumerate(reader, start=2):
            try:
                onset = float(row["onset_seconds"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid onset_seconds on CSV line {line_number}") from exc
            if not math.isfinite(onset) or onset < 0:
                raise ValueError(f"Invalid or negative onset_seconds on CSV line {line_number}")
            instrument = normalize_instrument(row["instrument"])
            if not instrument:
                raise ValueError(f"Empty instrument on CSV line {line_number}")
            events.append(Event(onset, instrument))
    return sorted(events)


def load_prediction(path: Path) -> list[Event]:
    try:
        import pretty_midi
    except ImportError as exc:
        raise RuntimeError("Install pretty-midi to read prediction files: pip install pretty-midi") from exc

    midi = pretty_midi.PrettyMIDI(str(path))
    drum_instruments = [instrument for instrument in midi.instruments if instrument.is_drum]
    if not drum_instruments:
        raise ValueError("MIDI contains no percussion/drum track (is_drum=True)")
    events = []
    for instrument in drum_instruments:
        for note in instrument.notes:
            label = GM_DRUM_MAP.get(note.pitch, f"unknown_{note.pitch}")
            events.append(Event(float(note.start), label))
    return sorted(events)


def _match_group(reference: list[Event], prediction: list[Event], tolerance: float) -> dict:
    """Greedy chronological one-to-one matching for a single instrument."""
    ref = sorted(reference)
    pred = sorted(prediction)
    used_prediction: set[int] = set()
    errors: list[float] = []
    matches = 0

    for ref_event in ref:
        candidates = [
            (abs(pred_event.onset_seconds - ref_event.onset_seconds), index)
            for index, pred_event in enumerate(pred)
            if index not in used_prediction
            and abs(pred_event.onset_seconds - ref_event.onset_seconds) <= tolerance
        ]
        if candidates:
            error, index = min(candidates)
            used_prediction.add(index)
            errors.append(error)
            matches += 1

    false_positives = len(pred) - matches
    false_negatives = len(ref) - matches
    precision = matches / len(pred) if pred else (1.0 if not ref else 0.0)
    recall = matches / len(ref) if ref else (1.0 if not pred else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_events": len(ref),
        "predicted_events": len(pred),
        "true_positives": matches,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_absolute_onset_error_ms": round(1000 * sum(errors) / len(errors), 2) if errors else None,
        "_onset_error_sum_seconds": sum(errors),
    }


def evaluate(reference: Iterable[Event], prediction: Iterable[Event], tolerance: float = 0.05) -> dict:
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    ref = list(reference)
    pred = list(prediction)
    labels = sorted({event.instrument for event in ref} | {event.instrument for event in pred})
    group_results = {
        label: _match_group(
            [event for event in ref if event.instrument == label],
            [event for event in pred if event.instrument == label],
            tolerance,
        )
        for label in labels
    }
    true_positives = sum(item["true_positives"] for item in group_results.values())
    false_positives = sum(item["false_positives"] for item in group_results.values())
    false_negatives = sum(item["false_negatives"] for item in group_results.values())
    reference_count = sum(item["reference_events"] for item in group_results.values())
    prediction_count = sum(item["predicted_events"] for item in group_results.values())
    precision = true_positives / prediction_count if prediction_count else (1.0 if not reference_count else 0.0)
    recall = true_positives / reference_count if reference_count else (1.0 if not prediction_count else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    error_sum = sum(item["_onset_error_sum_seconds"] for item in group_results.values())
    totals = {
        "reference_events": reference_count,
        "predicted_events": prediction_count,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_absolute_onset_error_ms": round(1000 * error_sum / true_positives, 2) if true_positives else None,
    }
    per_instrument = {
        label: {key: value for key, value in metrics.items() if not key.startswith("_")}
        for label, metrics in group_results.items()
    }
    return {
        "tolerance_ms": round(tolerance * 1000, 2),
        "overall": totals,
        "per_instrument": per_instrument,
        "notes": [
            "Instrument classification is exact: a hit on the wrong drum is one false positive plus one false negative.",
            "Onset matching is one-to-one and greedy within each instrument.",
            "This report measures event detection only; it does not score tempo-map, notation, or musical quality.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path, help="Human-annotated CSV")
    parser.add_argument("--prediction", required=True, type=Path, help="Predicted MIDI file")
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    report = evaluate(
        load_reference(args.reference),
        load_prediction(args.prediction),
        tolerance=args.tolerance_ms / 1000,
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
