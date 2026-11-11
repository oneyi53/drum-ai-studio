from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from drumscript.audio_processor.audio_loader import load_audio, normalise_audio
from drumscript.audio_processor.onset_detector import detect_onsets
from drumscript.datasets.idmt import find_mix_files, reference_onsets_for_file, subset_of
from drumscript.drum_classifier.classify import classify_events
from drumscript.notation_generator.constants import SAMPLE_RATE


def match_count(reference: list[float], estimates: list[float], tolerance: float) -> int:
    """Count one-to-one chronological matches within the timing tolerance."""
    refs = sorted(reference)
    preds = sorted(estimates)
    i = j = matched = 0
    while i < len(refs) and j < len(preds):
        delta = preds[j] - refs[i]
        if abs(delta) <= tolerance:
            matched += 1
            i += 1
            j += 1
        elif delta < -tolerance:
            j += 1
        else:
            i += 1
    return matched


def evaluate_file(audio_path: Path, tolerance: float) -> dict[str, int | float | str]:
    audio, sample_rate = load_audio(str(audio_path), sr=SAMPLE_RATE)
    audio = normalise_audio(audio)
    onsets = detect_onsets(audio, sample_rate)
    events = classify_events(audio, sample_rate, onsets)

    references_by_code = reference_onsets_for_file(audio_path)
    kick_references = references_by_code.get("KD", [])
    reference_times = [float(value) for value in kick_references]
    candidate_times = [float(value) for value in onsets]
    kick_times = sorted(
        float(event["time_sec"])
        for event in events
        if "kick" in event.get("instruments", [])
    )

    candidate_tp = match_count(reference_times, candidate_times, tolerance)
    kick_tp = match_count(reference_times, kick_times, tolerance)
    return {
        "track": audio_path.name,
        "subset": subset_of(audio_path),
        "kick_reference": len(reference_times),
        "onset_candidates": len(candidate_times),
        "candidate_matches": candidate_tp,
        "kick_predictions": len(kick_times),
        "kick_matches": kick_tp,
        "candidate_recall": candidate_tp / len(reference_times) if reference_times else 0.0,
        "kick_recall": kick_tp / len(reference_times) if reference_times else 0.0,
        "kick_precision": kick_tp / len(kick_times) if kick_times else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure kick-reference recall before and after DrumScript event classification."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--subset", choices=("RealDrum", "WaveDrum", "TechnoDrum"), required=True)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.limit < 1 or args.tolerance_ms < 0:
        parser.error("--limit must be positive and --tolerance-ms non-negative")

    files = find_mix_files(args.root, args.subset)[: args.limit]
    if not files:
        parser.error(f"No IDMT mix files found for subset {args.subset}")

    rows = [evaluate_file(path, args.tolerance_ms / 1000.0) for path in files]
    reference_total = sum(int(row["kick_reference"]) for row in rows)
    candidate_tp_total = sum(int(row["candidate_matches"]) for row in rows)
    kick_tp_total = sum(int(row["kick_matches"]) for row in rows)
    kick_prediction_total = sum(int(row["kick_predictions"]) for row in rows)

    summary = {
        "subset": args.subset,
        "tracks_evaluated": len(rows),
        "tolerance_ms": args.tolerance_ms,
        "kick_reference_events": reference_total,
        "onset_candidate_matches": candidate_tp_total,
        "kick_classification_matches": kick_tp_total,
        "kick_predictions": kick_prediction_total,
        "candidate_recall": candidate_tp_total / reference_total if reference_total else 0.0,
        "kick_recall": kick_tp_total / reference_total if reference_total else 0.0,
        "kick_precision": kick_tp_total / kick_prediction_total if kick_prediction_total else 0.0,
        "candidate_to_kick_match_retention": kick_tp_total / candidate_tp_total if candidate_tp_total else 0.0,
        "tracks": rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"KICK_STAGE_DIAGNOSTICS subset={args.subset} tracks={len(rows)} "
        f"refs={reference_total} candidate_recall={summary['candidate_recall']:.3f} "
        f"kick_recall={summary['kick_recall']:.3f} "
        f"kick_precision={summary['kick_precision']:.3f} "
        f"candidate_to_kick_retention={summary['candidate_to_kick_match_retention']:.3f}"
    )
    print(f"KICK_STAGE_ARTIFACT json={args.output} csv={csv_path}")


if __name__ == "__main__":
    main()
