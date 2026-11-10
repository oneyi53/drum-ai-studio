#!/usr/bin/env python3
"""Audit predicted drum-event CSVs for structural and suspicious output patterns.

This is a diagnostic report, not an accuracy score: without human annotations it
cannot determine whether a predicted hit is musically correct.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


REQUIRED = {"onset_seconds", "instrument", "pitch", "velocity", "duration_seconds"}


def audit_csv(path: Path, bin_seconds: float = 10.0) -> dict:
    if not math.isfinite(bin_seconds) or bin_seconds <= 0:
        raise ValueError("bin_seconds must be positive and finite")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError(f"CSV must contain columns: {', '.join(sorted(REQUIRED))}")
        rows = list(reader)

    events = []
    for line_number, row in enumerate(rows, start=2):
        try:
            onset = float(row["onset_seconds"])
            duration = float(row["duration_seconds"])
            pitch = int(row["pitch"])
            velocity = int(row["velocity"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric field on CSV line {line_number}") from exc
        if not math.isfinite(onset) or onset < 0:
            raise ValueError(f"Invalid onset_seconds on CSV line {line_number}")
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"Invalid duration_seconds on CSV line {line_number}")
        if not 0 <= velocity <= 127:
            raise ValueError(f"Velocity outside MIDI range on CSV line {line_number}")
        instrument = row["instrument"].strip()
        if not instrument:
            raise ValueError(f"Empty instrument on CSV line {line_number}")
        events.append({
            "onset": onset,
            "duration": duration,
            "pitch": pitch,
            "velocity": velocity,
            "instrument": instrument,
        })

    events.sort(key=lambda event: event["onset"])
    counts = Counter(event["instrument"] for event in events)
    velocities = Counter(event["velocity"] for event in events)
    durations = Counter(round(event["duration"], 6) for event in events)
    simultaneous = Counter((event["onset"], event["instrument"]) for event in events)
    duplicate_groups = [
        {"onset_seconds": onset, "instrument": instrument, "count": count}
        for (onset, instrument), count in simultaneous.items()
        if count > 1
    ]
    unknown = sum(label.startswith("unknown_") for label in counts)

    bins = Counter(int(event["onset"] // bin_seconds) for event in events)
    max_bin = int(events[-1]["onset"] // bin_seconds) if events else -1
    empty_bins = [
        round(index * bin_seconds, 3)
        for index in range(max_bin + 1)
        if bins[index] == 0
    ]

    warnings = []
    if events and len(velocities) == 1:
        warnings.append("All events have the same velocity; dynamics may not be represented.")
    if events and len(durations) == 1:
        warnings.append("All events have the same duration; note lengths may be template-based.")
    if duplicate_groups:
        warnings.append("Same-instrument events share identical onset timestamps; inspect possible duplicates.")
    if unknown:
        warnings.append("Unknown MIDI pitches were mapped to unknown instrument labels.")
    if empty_bins:
        warnings.append(f"No predicted events in {len(empty_bins)} time bins of {bin_seconds:g}s.")

    return {
        "source_csv": path.name,
        "event_count": len(events),
        "time_coverage_seconds": {
            "first_onset": round(events[0]["onset"], 6) if events else None,
            "last_onset": round(events[-1]["onset"], 6) if events else None,
        },
        "events_per_instrument": dict(sorted(counts.items())),
        "velocity_distribution": dict(sorted(velocities.items())),
        "duration_distribution_seconds": {
            str(value): count for value, count in sorted(durations.items())
        },
        "unknown_instrument_event_count": unknown,
        "same_onset_same_instrument_duplicate_groups": duplicate_groups,
        "empty_time_bins_seconds": empty_bins,
        "warnings": warnings,
        "interpretation": "Structural diagnostics only; not a precision/recall or musical-accuracy assessment.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_files", nargs="+", type=Path)
    parser.add_argument("--bin-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "bin_seconds": args.bin_seconds,
        "files": [audit_csv(path, args.bin_seconds) for path in args.csv_files],
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
